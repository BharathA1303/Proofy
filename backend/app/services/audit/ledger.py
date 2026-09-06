"""
backend/app/services/audit/ledger.py

Blockchain / Immutable Audit Ledger Abstraction & Development Hash-Chain Implementation.
Provides tamper-evident event anchoring and verification for the verification system.

DEVELOPMENT / SANDBOX LEDGER:
Explicitly labeled as development_sandbox. Zero claims of external or production government blockchain.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.schemas.audit import BlockchainBlock

logger = logging.getLogger(__name__)


def compute_block_hash(
    block_index: int,
    previous_hash: str,
    timestamp: float,
    target_id: str,
    event_type: str,
    evidence_hash: str,
    record_version: str,
    system_version: str,
    metadata: Dict[str, Any],
) -> str:
    """Deterministic canonical SHA-256 computation for an audit block."""
    payload = {
        "block_index": block_index,
        "previous_hash": previous_hash,
        "timestamp": round(timestamp, 4),
        "target_id": target_id,
        "event_type": event_type,
        "evidence_hash": evidence_hash,
        "record_version": record_version,
        "system_version": system_version,
        "metadata": metadata,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class BlockchainLedger(ABC):
    """Abstract interface for audit ledgers."""

    @property
    @abstractmethod
    def ledger_name(self) -> str:
        """Human-readable ledger identifier."""
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Ledger operational category (e.g., 'development_sandbox')."""
        pass

    @abstractmethod
    def append_block(
        self,
        target_id: str,
        event_type: str,
        evidence_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BlockchainBlock:
        """Append an immutable block to the chain."""
        pass

    @abstractmethod
    def get_chain(self, target_id: Optional[str] = None) -> List[BlockchainBlock]:
        """Retrieve all blocks, optionally filtered by verification_id or case_id."""
        pass

    @abstractmethod
    def get_latest_block(self, target_id: Optional[str] = None) -> Optional[BlockchainBlock]:
        """Retrieve the most recent block."""
        pass

    @abstractmethod
    def verify_chain(self, target_id: Optional[str] = None) -> Tuple[bool, str]:
        """Verify the cryptographic hash-chain integrity of the ledger."""
        pass


class DevelopmentBlockchainLedger(BlockchainLedger):
    """
    In-memory and file-backed cryptographic hash-chain ledger for development and SIH demos.
    Maintains a strictly ordered SHA-256 hash sequence anchored from a genesis block.
    """

    def __init__(
        self,
        persistence_path: Optional[str] = None,
        storage_path: Optional[str] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._chain: List[BlockchainBlock] = []
        eff_path = persistence_path or storage_path
        self._persistence_path = Path(eff_path) if eff_path else None
        self._storage_path = str(self._persistence_path) if self._persistence_path else None
        self._initialize_ledger()

    @property
    def ledger_name(self) -> str:
        return "LOCAL DEVELOPMENT LEDGER"

    @property
    def source_type(self) -> str:
        return "development_sandbox"

    def get_block_count(self) -> int:
        with self._lock:
            return len(self._chain)

    def get_block(self, index: int) -> Optional[BlockchainBlock]:
        with self._lock:
            if 0 <= index < len(self._chain):
                return self._chain[index]
            return None

    def append_event(
        self,
        event_type: str,
        target_id: str,
        payload: Optional[Dict[str, Any]] = None,
        event_hash: str = "",
    ) -> BlockchainBlock:
        return self.append_block(
            target_id=target_id,
            event_type=event_type,
            evidence_hash=event_hash or "0" * 64,
            metadata=payload or {},
        )

    def verify_chain_integrity(self, target_id: Optional[str] = None) -> Tuple[bool, str]:
        return self.verify_chain(target_id=target_id)

    def _initialize_ledger(self) -> None:
        """Load from disk or generate Genesis block."""
        if self._persistence_path and self._persistence_path.exists():
            try:
                with open(self._persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._chain = [BlockchainBlock(**block_dict) for block_dict in data]
                logger.info(
                    "DevelopmentBlockchainLedger: loaded %d blocks from %s",
                    len(self._chain), self._persistence_path,
                )
                return
            except Exception as exc:
                logger.warning(
                    "DevelopmentBlockchainLedger: failed to load existing ledger (%s). Recreating genesis block.",
                    exc,
                )

        # Generate Genesis Block
        t_now = time.time()
        genesis_prev = "0" * 64
        genesis_meta = {
            "genesis_note": "AI-Based Fake Identity & Document Screening System Audit Ledger",
            "environment": settings.ENVIRONMENT,
        }
        genesis_hash = compute_block_hash(
            block_index=0,
            previous_hash=genesis_prev,
            timestamp=t_now,
            target_id="SYSTEM",
            event_type="GENESIS",
            evidence_hash="0" * 64,
            record_version="1.0.0",
            system_version=settings.APP_VERSION,
            metadata=genesis_meta,
        )
        genesis_block = BlockchainBlock(
            block_index=0,
            previous_hash=genesis_prev,
            block_hash=genesis_hash,
            timestamp=t_now,
            target_id="SYSTEM",
            event_type="GENESIS",
            evidence_hash="0" * 64,
            record_version="1.0.0",
            system_version=settings.APP_VERSION,
            metadata=genesis_meta,
        )
        self._chain = [genesis_block]
        self._persist_to_disk()

    def _persist_to_disk(self) -> None:
        """Safely persist blocks to file if path is specified."""
        if not self._persistence_path:
            return
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._persistence_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump([b.model_dump() for b in self._chain], f, indent=2)
            os.replace(temp_path, self._persistence_path)
        except Exception as exc:
            # Resilience: never crash caller if disk write fails
            logger.warning("DevelopmentBlockchainLedger: failed to persist ledger to disk: %s", exc)

    def append_block(
        self,
        target_id: str,
        event_type: str,
        evidence_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BlockchainBlock:
        with self._lock:
            latest = self._chain[-1]
            new_index = latest.block_index + 1
            prev_hash = latest.block_hash
            t_now = time.time()
            meta = metadata or {}

            block_hash = compute_block_hash(
                block_index=new_index,
                previous_hash=prev_hash,
                timestamp=t_now,
                target_id=target_id,
                event_type=event_type,
                evidence_hash=evidence_hash,
                record_version="1.0.0",
                system_version=settings.APP_VERSION,
                metadata=meta,
            )

            block = BlockchainBlock(
                block_index=new_index,
                previous_hash=prev_hash,
                block_hash=block_hash,
                timestamp=t_now,
                target_id=target_id,
                event_type=event_type,
                evidence_hash=evidence_hash,
                record_version="1.0.0",
                system_version=settings.APP_VERSION,
                metadata=meta,
            )
            self._chain.append(block)
            self._persist_to_disk()
            logger.info(
                "DevelopmentBlockchainLedger: appended block #%d event=%s target=%s hash=%s...",
                new_index, event_type, target_id, block_hash[:12],
            )
            return block

    def get_chain(self, target_id: Optional[str] = None) -> List[BlockchainBlock]:
        with self._lock:
            if not target_id:
                return list(self._chain)
            return [b for b in self._chain if b.target_id == target_id or b.block_index == 0]

    def get_latest_block(self, target_id: Optional[str] = None) -> Optional[BlockchainBlock]:
        with self._lock:
            chain = self.get_chain(target_id)
            return chain[-1] if chain else None

    def verify_chain(self, target_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Verify that:
        1. Genesis block is valid.
        2. Each subsequent block correctly hashes the previous block's hash.
        3. Each block's contents match its block_hash.
        """
        with self._lock:
            chain = self._chain
            if not chain:
                return False, "Ledger is empty"

            # 1. Verify Genesis Block
            genesis = chain[0]
            if genesis.block_index != 0 or genesis.previous_hash != "0" * 64:
                return False, "Invalid genesis block parameters"

            expected_genesis_hash = compute_block_hash(
                block_index=0,
                previous_hash="0" * 64,
                timestamp=genesis.timestamp,
                target_id=genesis.target_id,
                event_type=genesis.event_type,
                evidence_hash=genesis.evidence_hash,
                record_version=genesis.record_version,
                system_version=genesis.system_version,
                metadata=genesis.metadata,
            )
            if genesis.block_hash != expected_genesis_hash:
                return False, f"Genesis block hash corrupted: {genesis.block_hash} != {expected_genesis_hash}"

            # 2. Verify subsequent blocks
            for i in range(1, len(chain)):
                curr = chain[i]
                prev = chain[i - 1]

                # Linkage verification
                if curr.previous_hash != prev.block_hash:
                    return False, f"Broken link at block #{curr.block_index}: previous_hash does not match block #{prev.block_index} hash"

                # Content hash verification
                expected_hash = compute_block_hash(
                    block_index=curr.block_index,
                    previous_hash=curr.previous_hash,
                    timestamp=curr.timestamp,
                    target_id=curr.target_id,
                    event_type=curr.event_type,
                    evidence_hash=curr.evidence_hash,
                    record_version=curr.record_version,
                    system_version=curr.system_version,
                    metadata=curr.metadata,
                )
                if curr.block_hash != expected_hash:
                    return False, f"Block #{curr.block_index} hash mismatch (tampered block content)"

            return True, f"All {len(chain)} blocks in ledger verified successfully"


# Singleton instance configured with settings
blockchain_ledger = DevelopmentBlockchainLedger(
    persistence_path=settings.BLOCKCHAIN_CHAIN_STORAGE_PATH if settings.BLOCKCHAIN_ENABLED else None
)
