"""
Whale Wallet Clustering & Labeling Module

This module implements heuristics for address clustering and linking to known entity labels.
It processes whale transactions to identify patterns, cluster related addresses,
and build a wallet network store for tracking smart money movements.

Features:
- Address clustering based on transaction patterns
- Entity labeling (exchange, whale, smart money, etc.)
- Network analysis for wallet relationships
- Batch and streaming processing support
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


class WhaleWalletClusterer:
    """
    Implements whale wallet clustering and labeling using heuristics.
    
    Clustering heuristics:
    1. Common input heuristic: Addresses used as inputs in same tx are likely controlled by same entity
    2. Change address heuristic: Change outputs often go back to same entity
    3. Temporal clustering: Addresses active in similar time windows
    4. Value clustering: Similar transaction amounts suggest related addresses
    5. Exchange deposit/withdrawal patterns
    """
    
    def __init__(self, database):
        self.database = database
        
        # Known entity labels (can be extended with external data sources)
        self.known_entities = {
            # Exchanges
            "binance": {"type": "exchange", "keywords": ["binance", "bnb"]},
            "coinbase": {"type": "exchange", "keywords": ["coinbase", "cb"]},
            "kraken": {"type": "exchange", "keywords": ["kraken"]},
            "huobi": {"type": "exchange", "keywords": ["huobi", "hb"]},
            "okx": {"type": "exchange", "keywords": ["okx", "okex"]},
            "bybit": {"type": "exchange", "keywords": ["bybit"]},
            "kucoin": {"type": "exchange", "keywords": ["kucoin", "kcs"]},
            "gate.io": {"type": "exchange", "keywords": ["gate", "gateio"]},
            
            # DeFi Protocols
            "uniswap": {"type": "defi_protocol", "keywords": ["uniswap", "uni"]},
            "aave": {"type": "defi_protocol", "keywords": ["aave"]},
            "compound": {"type": "defi_protocol", "keywords": ["compound", "comp"]},
            "maker": {"type": "defi_protocol", "keywords": ["maker", "mkr"]},
            "curve": {"type": "defi_protocol", "keywords": ["curve", "crv"]},
            
            # Bridges
            "wormhole": {"type": "bridge", "keywords": ["wormhole"]},
            "multichain": {"type": "bridge", "keywords": ["multichain", "anyswap"]},
            
            # Smart Money (example addresses - would be populated from data sources)
            "whale_1": {"type": "whale", "keywords": []},
        }
        
        # Clustering parameters
        self.temporal_window_hours = 24  # Cluster addresses active within 24h
        self.value_similarity_threshold = 0.9  # 90% similarity for value clustering
        self.min_cluster_size = 2
        self.max_cluster_size = 1000
        
        # Caches
        self.address_clusters: Dict[str, str] = {}  # address -> cluster_id
        self.cluster_metadata: Dict[str, Dict] = {}  # cluster_id -> metadata
        
    async def label_address(self, address: str, from_label: Optional[str] = None, 
                           to_label: Optional[str] = None) -> Dict[str, Any]:
        """
        Label an address based on available information.
        
        Args:
            address: Wallet address to label
            from_label: Label from transaction source (if available)
            to_label: Label from transaction destination (if available)
            
        Returns:
            Dict containing label information
        """
        label_info = {
            "address": address,
            "primary_label": "unknown",
            "category": "unknown",
            "confidence": 0.0,
            "sources": [],
            "metadata": {}
        }
        
        # Check if we have existing label in database
        existing_label = await self.database.get_wallet_label_by_address(address)
        if existing_label:
            return existing_label
            
        # Try to match against known entities
        address_lower = address.lower()
        for entity_name, entity_info in self.known_entities.items():
            for keyword in entity_info["keywords"]:
                if keyword in address_lower:
                    label_info["primary_label"] = entity_name
                    label_info["category"] = entity_info["type"]
                    label_info["confidence"] = 0.8
                    label_info["sources"].append("keyword_match")
                    break
                    
        # Use transaction labels if available
        if from_label and from_label != "unknown":
            if label_info["primary_label"] == "unknown":
                label_info["primary_label"] = f"related_to_{from_label}"
                label_info["category"] = "related"
                label_info["confidence"] = 0.5
                label_info["sources"].append("from_label")
                
        if to_label and to_label != "unknown":
            if label_info["primary_label"] == "unknown":
                label_info["primary_label"] = f"related_to_{to_label}"
                label_info["category"] = "related"
                label_info["confidence"] = 0.5
                label_info["sources"].append("to_label")
                
        # Store label in database
        await self.database.store_wallet_label({
            "address": address,
            "label": label_info["primary_label"],
            "category": label_info["category"],
            "confidence": label_info["confidence"],
            "sources": label_info["sources"],
            "metadata": label_info["metadata"],
            "updated_at": datetime.utcnow().isoformat()
        })
        
        return label_info
        
    def _generate_cluster_id(self, addresses: Set[str]) -> str:
        """Generate deterministic cluster ID from addresses."""
        sorted_addresses = sorted(addresses)
        hash_input = "|".join(sorted_addresses)
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        
    async def cluster_addresses_by_temporal_pattern(
        self, 
        transactions: List[Dict], 
        window_hours: int = 24
    ) -> Dict[str, Set[str]]:
        """
        Cluster addresses that are active in similar time windows.
        
        Args:
            transactions: List of whale transactions
            window_hours: Time window for clustering (default 24h)
            
        Returns:
            Dict mapping cluster_id to set of addresses
        """
        # Group transactions by time windows
        time_windows: Dict[str, Set[str]] = defaultdict(set)
        
        for tx in transactions:
            timestamp = tx.get("timestamp")
            if not timestamp:
                continue
                
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                
            # Round to time window
            window_start = timestamp.replace(minute=0, second=0, microsecond=0)
            window_start = window_start - timedelta(hours=window_start.hour % window_hours)
            window_key = window_start.isoformat()
            
            # Add addresses to this window
            from_addr = tx.get("from_address")
            to_addr = tx.get("to_address")
            
            if from_addr:
                time_windows[window_key].add(from_addr)
            if to_addr:
                time_windows[window_key].add(to_addr)
                
        # Create clusters from overlapping windows
        clusters: Dict[str, Set[str]] = {}
        for window_key, addresses in time_windows.items():
            if len(addresses) >= self.min_cluster_size:
                cluster_id = self._generate_cluster_id(addresses)
                if cluster_id not in clusters:
                    clusters[cluster_id] = addresses
                else:
                    clusters[cluster_id].update(addresses)
                    
        return clusters
        
    async def cluster_addresses_by_value_pattern(
        self, 
        transactions: List[Dict]
    ) -> Dict[str, Set[str]]:
        """
        Cluster addresses with similar transaction value patterns.
        
        Args:
            transactions: List of whale transactions
            
        Returns:
            Dict mapping cluster_id to set of addresses
        """
        # Group addresses by value ranges
        value_ranges: Dict[Tuple[float, float], Set[str]] = defaultdict(set)
        
        for tx in transactions:
            amount = tx.get("amount_usd", 0)
            if amount <= 0:
                continue
                
            # Create value range buckets (logarithmic)
            import math
            log_amount = math.log10(amount)
            range_start = 10 ** int(log_amount)
            range_end = 10 ** (int(log_amount) + 1)
            range_key = (range_start, range_end)
            
            from_addr = tx.get("from_address")
            to_addr = tx.get("to_address")
            
            if from_addr:
                value_ranges[range_key].add(from_addr)
            if to_addr:
                value_ranges[range_key].add(to_addr)
                
        # Create clusters from value ranges
        clusters: Dict[str, Set[str]] = {}
        for range_key, addresses in value_ranges.items():
            if len(addresses) >= self.min_cluster_size:
                cluster_id = self._generate_cluster_id(addresses)
                clusters[cluster_id] = addresses
                
        return clusters
        
    async def cluster_addresses_by_common_input(
        self, 
        transactions: List[Dict]
    ) -> Dict[str, Set[str]]:
        """
        Cluster addresses that appear together as inputs in transactions.
        (Common input heuristic - addresses used together likely controlled by same entity)
        
        Args:
            transactions: List of whale transactions
            
        Returns:
            Dict mapping cluster_id to set of addresses
        """
        # Build transaction groups
        tx_groups: Dict[str, Set[str]] = defaultdict(set)
        
        for tx in transactions:
            tx_hash = tx.get("tx_hash", tx.get("transaction_hash"))
            if not tx_hash:
                continue
                
            from_addr = tx.get("from_address")
            if from_addr:
                tx_groups[tx_hash].add(from_addr)
                
        # Create clusters from transaction groups
        clusters: Dict[str, Set[str]] = {}
        for tx_hash, addresses in tx_groups.items():
            if len(addresses) >= self.min_cluster_size:
                cluster_id = self._generate_cluster_id(addresses)
                if cluster_id not in clusters:
                    clusters[cluster_id] = addresses
                else:
                    clusters[cluster_id].update(addresses)
                    
        return clusters
        
    async def merge_clusters(
        self, 
        clusters_list: List[Dict[str, Set[str]]]
    ) -> Dict[str, Set[str]]:
        """
        Merge overlapping clusters from different clustering methods.
        
        Args:
            clusters_list: List of cluster dictionaries
            
        Returns:
            Merged clusters
        """
        if not clusters_list:
            return {}
            
        # Union-find for merging
        parent: Dict[str, str] = {}
        
        def find(addr: str) -> str:
            if addr not in parent:
                parent[addr] = addr
            if parent[addr] != addr:
                parent[addr] = find(parent[addr])
            return parent[addr]
            
        def union(addr1: str, addr2: str):
            root1 = find(addr1)
            root2 = find(addr2)
            if root1 != root2:
                parent[root2] = root1
                
        # Merge all clusters
        for clusters in clusters_list:
            for cluster_id, addresses in clusters.items():
                addr_list = list(addresses)
                for i in range(len(addr_list) - 1):
                    union(addr_list[i], addr_list[i + 1])
                    
        # Build final clusters
        final_clusters: Dict[str, Set[str]] = defaultdict(set)
        for addr in parent:
            root = find(addr)
            final_clusters[root].add(addr)
            
        # Rename clusters with deterministic IDs
        renamed_clusters = {}
        for addresses in final_clusters.values():
            if len(addresses) >= self.min_cluster_size and len(addresses) <= self.max_cluster_size:
                cluster_id = self._generate_cluster_id(addresses)
                renamed_clusters[cluster_id] = addresses
                
        return renamed_clusters
        
    async def build_wallet_network(
        self, 
        transactions: List[Dict]
    ) -> Dict[str, Any]:
        """
        Build a network graph of wallet relationships.
        
        Args:
            transactions: List of whale transactions
            
        Returns:
            Network data structure
        """
        network = {
            "nodes": {},  # address -> node data
            "edges": [],  # transaction relationships
            "clusters": {}  # cluster_id -> cluster data
        }
        
        # Build nodes
        addresses = set()
        for tx in transactions:
            from_addr = tx.get("from_address")
            to_addr = tx.get("to_address")
            
            if from_addr:
                addresses.add(from_addr)
            if to_addr:
                addresses.add(to_addr)
                
        # Label all addresses
        for addr in addresses:
            label = await self.label_address(addr)
            network["nodes"][addr] = {
                "address": addr,
                "label": label["primary_label"],
                "category": label["category"],
                "confidence": label["confidence"],
                "tx_count": 0,
                "total_volume": 0.0
            }
            
        # Build edges
        for tx in transactions:
            from_addr = tx.get("from_address")
            to_addr = tx.get("to_address")
            amount = tx.get("amount_usd", 0)
            
            if from_addr and to_addr:
                network["edges"].append({
                    "from": from_addr,
                    "to": to_addr,
                    "amount_usd": amount,
                    "timestamp": tx.get("timestamp"),
                    "tx_hash": tx.get("tx_hash", tx.get("transaction_hash"))
                })
                
                # Update node metrics
                if from_addr in network["nodes"]:
                    network["nodes"][from_addr]["tx_count"] += 1
                    network["nodes"][from_addr]["total_volume"] += amount
                if to_addr in network["nodes"]:
                    network["nodes"][to_addr]["tx_count"] += 1
                    
        return network
        
    async def process_whale_transactions_batch(
        self, 
        hours: int = 24,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Process whale transactions in batch mode for clustering and labeling.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum transactions to process
            
        Returns:
            Processing results with clusters and labels
        """
        logger.info(f"Starting batch processing of whale transactions (last {hours} hours)")
        
        # Fetch recent whale transactions
        transactions = await self.database.get_whale_transactions(
            hours=hours,
            limit=limit
        )
        
        if not transactions:
            logger.warning("No whale transactions found for clustering")
            return {
                "status": "no_data",
                "transactions_processed": 0,
                "clusters_found": 0
            }
            
        logger.info(f"Processing {len(transactions)} whale transactions")
        
        # Apply different clustering methods
        temporal_clusters = await self.cluster_addresses_by_temporal_pattern(transactions)
        value_clusters = await self.cluster_addresses_by_value_pattern(transactions)
        common_input_clusters = await self.cluster_addresses_by_common_input(transactions)
        
        # Merge clusters
        all_clusters = await self.merge_clusters([
            temporal_clusters,
            value_clusters,
            common_input_clusters
        ])
        
        logger.info(f"Found {len(all_clusters)} merged clusters")
        
        # Store clusters in database
        for cluster_id, addresses in all_clusters.items():
            # Calculate cluster metadata
            cluster_txs = [tx for tx in transactions 
                          if tx.get("from_address") in addresses or tx.get("to_address") in addresses]
            
            total_volume = sum(tx.get("amount_usd", 0) for tx in cluster_txs)
            avg_volume = total_volume / len(cluster_txs) if cluster_txs else 0
            
            # Determine cluster label based on most common address label
            address_labels = []
            for addr in addresses:
                label = await self.label_address(addr)
                address_labels.append(label["category"])
                
            from collections import Counter
            most_common_category = Counter(address_labels).most_common(1)[0][0] if address_labels else "unknown"
            
            cluster_data = {
                "cluster_id": cluster_id,
                "addresses": list(addresses),
                "address_count": len(addresses),
                "transaction_count": len(cluster_txs),
                "total_volume_usd": total_volume,
                "average_volume_usd": avg_volume,
                "category": most_common_category,
                "first_seen": min(tx.get("timestamp") for tx in cluster_txs) if cluster_txs else None,
                "last_seen": max(tx.get("timestamp") for tx in cluster_txs) if cluster_txs else None,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Store in wallet_network_store
            await self.database.store_wallet_cluster(cluster_data)
            
        # Build network graph
        network = await self.build_wallet_network(transactions)
        
        return {
            "status": "success",
            "transactions_processed": len(transactions),
            "clusters_found": len(all_clusters),
            "unique_addresses": len(network["nodes"]),
            "network_edges": len(network["edges"]),
            "clusters": all_clusters,
            "network": network
        }
        
    async def process_whale_transaction_streaming(
        self, 
        transaction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a single whale transaction in streaming mode.
        Update clusters and labels in real-time.
        
        Args:
            transaction: Single whale transaction
            
        Returns:
            Processing result
        """
        from_addr = transaction.get("from_address")
        to_addr = transaction.get("to_address")
        
        # Label addresses
        from_label = await self.label_address(
            from_addr, 
            from_label=transaction.get("from_label"),
            to_label=transaction.get("to_label")
        ) if from_addr else None
        
        to_label = await self.label_address(
            to_addr,
            from_label=transaction.get("from_label"),
            to_label=transaction.get("to_label")
        ) if to_addr else None
        
        # Check if addresses belong to existing clusters
        from_cluster = await self.database.get_cluster_by_address(from_addr) if from_addr else None
        to_cluster = await self.database.get_cluster_by_address(to_addr) if to_addr else None
        
        # Update or create cluster
        if from_cluster and to_cluster and from_cluster["cluster_id"] == to_cluster["cluster_id"]:
            # Both in same cluster, update metrics
            cluster_id = from_cluster["cluster_id"]
            await self.database.update_cluster_metrics(
                cluster_id, 
                transaction.get("amount_usd", 0)
            )
        elif from_cluster or to_cluster:
            # One address in cluster, add the other
            cluster = from_cluster or to_cluster
            new_addr = to_addr if from_cluster else from_addr
            
            if new_addr:
                await self.database.add_address_to_cluster(
                    cluster["cluster_id"],
                    new_addr
                )
        else:
            # Neither in cluster, create new cluster if both addresses present
            if from_addr and to_addr:
                addresses = {from_addr, to_addr}
                cluster_id = self._generate_cluster_id(addresses)
                
                cluster_data = {
                    "cluster_id": cluster_id,
                    "addresses": list(addresses),
                    "address_count": 2,
                    "transaction_count": 1,
                    "total_volume_usd": transaction.get("amount_usd", 0),
                    "average_volume_usd": transaction.get("amount_usd", 0),
                    "category": from_label["category"] if from_label else "unknown",
                    "first_seen": transaction.get("timestamp"),
                    "last_seen": transaction.get("timestamp"),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                await self.database.store_wallet_cluster(cluster_data)
                
        return {
            "status": "processed",
            "from_address": from_addr,
            "to_address": to_addr,
            "from_label": from_label["primary_label"] if from_label else None,
            "to_label": to_label["primary_label"] if to_label else None,
            "cluster_updated": from_cluster is not None or to_cluster is not None
        }
