// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// ============================================================================
// SOSTEscrowV2 — PoPC Model B Timelocked Gold Escrow with Beneficiary Support
//
// Evolution of SOSTEscrow with transferable beneficiary rights.
// When a position trades inside SOST, the beneficiary can be reassigned
// so the new economic owner receives the principal at maturity.
//
// Properties (constitutional, immutable):
//   - NO admin key
//   - NO upgrade proxy (no UUPS, no transparent proxy, no beacon)
//   - NO pause function
//   - NO emergency withdrawal
//   - NO extension or modification of existing deposits
//   - ONLY the current beneficiary can withdraw or reassign
//   - ONLY after the timelock expires (for withdrawal)
//   - Source code published and verified on block explorer
//
// Trust model:
//   - The contract itself is trustless (immutable, no admin)
//   - Whoever owns the principal economically can reassign the payout address
//   - Only the currentBeneficiary can call updateBeneficiary or withdraw
//   - The SOST reward payout is handled OFF-CHAIN by the watcher
//
// SOST Protocol — Copyright (c) 2026 SOST Protocol
// MIT License. See LICENSE file.
// ============================================================================

import {IERC20} from "./interfaces/IERC20.sol";
import {ReentrancyGuard} from "./security/ReentrancyGuard.sol";

contract SOSTEscrowV2 is ReentrancyGuard {

    // ---- Structs ----

    struct Deposit {
        address depositor;          // original depositor (for record-keeping)
        address currentBeneficiary; // who receives tokens on withdraw (transferable)
        address token;              // ERC-20 token address (XAUT or PAXG)
        uint256 amount;             // amount deposited (in token's smallest unit)
        uint256 unlockTime;         // Unix timestamp when withdrawal becomes possible
        bool    withdrawn;          // true after successful withdrawal
    }

    // ---- State ----

    address public immutable XAUT;
    address public immutable PAXG;

    uint256 public constant MIN_LOCK_DURATION = 28 days;
    uint256 public constant MAX_LOCK_DURATION = 366 days;

    uint256 public constant XAUT_MIN_AMOUNT = 1000;    // 0.001 oz (1e3 in 6-decimal token)
    uint256 public constant PAXG_MIN_AMOUNT = 1e15;     // 0.001 oz (1e15 in 18-decimal token)

    uint256 public depositCount;

    mapping(uint256 => Deposit) public deposits;
    mapping(address => uint256[]) internal _userDepositIds;
    mapping(address => uint256) public totalLockedByToken;

    // ---- Events ----

    event GoldDeposited(
        uint256 indexed depositId,
        address indexed depositor,
        address indexed token,
        uint256 amount,
        uint256 unlockTime,
        address beneficiary
    );

    event GoldWithdrawn(
        uint256 indexed depositId,
        address indexed beneficiary,
        address token,
        uint256 amount
    );

    event BeneficiaryUpdated(
        uint256 indexed depositId,
        address oldBeneficiary,
        address newBeneficiary
    );

    // ---- Errors ----

    error TokenNotAllowed(address token);
    error AmountBelowMinimum(uint256 amount, uint256 minimum);
    error UnlockTimeNotInFuture(uint256 unlockTime, uint256 currentTime);
    error LockDurationTooShort(uint256 duration, uint256 minimum);
    error LockDurationTooLong(uint256 duration, uint256 maximum);
    error DepositNotFound(uint256 depositId);
    error NotBeneficiary(address caller, address beneficiary);
    error StillLocked(uint256 unlockTime, uint256 currentTime);
    error AlreadyWithdrawn(uint256 depositId);
    error ZeroAddress();
    error TransferFailed();

    // ---- Constructor ----

    constructor(address _xaut, address _paxg) {
        require(_xaut != address(0), "XAUT address cannot be zero");
        require(_paxg != address(0), "PAXG address cannot be zero");
        require(_xaut != _paxg, "XAUT and PAXG must be different");
        XAUT = _xaut;
        PAXG = _paxg;
    }

    // ---- Core functions ----

    /// @notice Deposit gold tokens into escrow with a timelock. Beneficiary defaults to msg.sender.
    function deposit(
        address token,
        uint256 amount,
        uint256 unlockTime
    )
        external
        nonReentrant
        returns (uint256 depositId)
    {
        return _deposit(token, amount, unlockTime, msg.sender);
    }

    /// @notice Deposit gold tokens into escrow with a timelock and a specified beneficiary.
    function depositFor(
        address token,
        uint256 amount,
        uint256 unlockTime,
        address beneficiary
    )
        external
        nonReentrant
        returns (uint256 depositId)
    {
        if (beneficiary == address(0)) {
            revert ZeroAddress();
        }
        return _deposit(token, amount, unlockTime, beneficiary);
    }

    /// @notice Update the beneficiary of a deposit. ONLY callable by current beneficiary.
    function updateBeneficiary(uint256 depositId, address newBeneficiary) external {
        Deposit storage d = deposits[depositId];

        if (d.depositor == address(0)) {
            revert DepositNotFound(depositId);
        }
        if (msg.sender != d.currentBeneficiary) {
            revert NotBeneficiary(msg.sender, d.currentBeneficiary);
        }
        if (newBeneficiary == address(0)) {
            revert ZeroAddress();
        }

        address oldBeneficiary = d.currentBeneficiary;
        d.currentBeneficiary = newBeneficiary;

        emit BeneficiaryUpdated(depositId, oldBeneficiary, newBeneficiary);
    }

    /// @notice Withdraw gold tokens after the timelock has expired. Sends to currentBeneficiary.
    function withdraw(uint256 depositId) external nonReentrant {
        Deposit storage d = deposits[depositId];

        // --- CHECKS ---

        if (d.depositor == address(0)) {
            revert DepositNotFound(depositId);
        }
        if (msg.sender != d.currentBeneficiary) {
            revert NotBeneficiary(msg.sender, d.currentBeneficiary);
        }
        if (d.withdrawn) {
            revert AlreadyWithdrawn(depositId);
        }
        if (block.timestamp < d.unlockTime) {
            revert StillLocked(d.unlockTime, block.timestamp);
        }

        // --- EFFECTS ---

        d.withdrawn = true;
        totalLockedByToken[d.token] -= d.amount;

        // --- INTERACTIONS ---

        bool success = IERC20(d.token).transfer(d.currentBeneficiary, d.amount);
        if (!success) {
            revert TransferFailed();
        }

        emit GoldWithdrawn(depositId, d.currentBeneficiary, d.token, d.amount);
    }

    // ---- Internal ----

    function _deposit(
        address token,
        uint256 amount,
        uint256 unlockTime,
        address beneficiary
    )
        internal
        returns (uint256 depositId)
    {
        if (token != XAUT && token != PAXG) {
            revert TokenNotAllowed(token);
        }

        uint256 minAmount = (token == XAUT) ? XAUT_MIN_AMOUNT : PAXG_MIN_AMOUNT;
        if (amount < minAmount) {
            revert AmountBelowMinimum(amount, minAmount);
        }

        if (unlockTime <= block.timestamp) {
            revert UnlockTimeNotInFuture(unlockTime, block.timestamp);
        }

        uint256 duration = unlockTime - block.timestamp;
        if (duration < MIN_LOCK_DURATION) {
            revert LockDurationTooShort(duration, MIN_LOCK_DURATION);
        }
        if (duration > MAX_LOCK_DURATION) {
            revert LockDurationTooLong(duration, MAX_LOCK_DURATION);
        }

        // INTERACTION: transfer tokens first
        bool success = IERC20(token).transferFrom(msg.sender, address(this), amount);
        if (!success) {
            revert TransferFailed();
        }

        // EFFECTS: record deposit only after successful transfer
        depositId = depositCount;
        depositCount++;

        deposits[depositId] = Deposit({
            depositor: msg.sender,
            currentBeneficiary: beneficiary,
            token: token,
            amount: amount,
            unlockTime: unlockTime,
            withdrawn: false
        });

        _userDepositIds[msg.sender].push(depositId);
        totalLockedByToken[token] += amount;

        emit GoldDeposited(depositId, msg.sender, token, amount, unlockTime, beneficiary);
    }

    // ---- View functions ----

    function getUserDepositIds(address user) external view returns (uint256[] memory) {
        return _userDepositIds[user];
    }

    function getDeposit(uint256 depositId) external view returns (
        address depositor,
        address currentBeneficiary,
        address token,
        uint256 amount,
        uint256 unlockTime,
        bool withdrawn
    ) {
        Deposit storage d = deposits[depositId];
        return (d.depositor, d.currentBeneficiary, d.token, d.amount, d.unlockTime, d.withdrawn);
    }

    function canWithdraw(uint256 depositId) external view returns (bool) {
        Deposit storage d = deposits[depositId];
        if (d.depositor == address(0)) return false;
        if (d.withdrawn) return false;
        return block.timestamp >= d.unlockTime;
    }

    function totalLocked(address token) external view returns (uint256) {
        return totalLockedByToken[token];
    }
}
