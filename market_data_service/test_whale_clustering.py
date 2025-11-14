"""
Tests for Whale Wallet Clustering & Labeling

Tests cover:
- Address labeling (known entities, heuristics)
- Clustering algorithms (temporal, value, common input)
- Cluster merging
- Network building
- Batch processing
- Streaming processing
- Database operations
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whale_wallet_clustering import WhaleWalletClusterer


@pytest.fixture
def mock_database():
    """Create mock database for testing"""
    db = AsyncMock()
    
    # Mock wallet label methods
    db.get_wallet_label_by_address = AsyncMock(return_value=None)
    db.store_wallet_label = AsyncMock(return_value=True)
    db.store_wallet_cluster = AsyncMock(return_value=True)
    db.get_cluster_by_address = AsyncMock(return_value=None)
    db.update_cluster_metrics = AsyncMock(return_value=True)
    db.add_address_to_cluster = AsyncMock(return_value=True)
    db.get_all_clusters = AsyncMock(return_value=[])
    db.get_whale_transactions = AsyncMock(return_value=[])
    
    return db


@pytest.fixture
def sample_transactions():
    """Create sample whale transactions for testing"""
    base_time = datetime.utcnow()
    
    return [
        {
            "tx_hash": "0x1111111111111111111111111111111111111111",
            "from_address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "amount_usd": 1000000,
            "timestamp": (base_time - timedelta(hours=1)).isoformat(),
            "from_label": "unknown",
            "to_label": "binance"
        },
        {
            "tx_hash": "0x2222222222222222222222222222222222222222",
            "from_address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to_address": "0xcccccccccccccccccccccccccccccccccccccccc",
            "amount_usd": 950000,
            "timestamp": (base_time - timedelta(hours=2)).isoformat(),
            "from_label": "unknown",
            "to_label": "unknown"
        },
        {
            "tx_hash": "0x3333333333333333333333333333333333333333",
            "from_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "to_address": "0xdddddddddddddddddddddddddddddddddddddddd",
            "amount_usd": 2000000,
            "timestamp": (base_time - timedelta(hours=3)).isoformat(),
            "from_label": "binance",
            "to_label": "unknown"
        },
        {
            "tx_hash": "0x4444444444444444444444444444444444444444",
            "from_address": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            "to_address": "0xffffffffffffffffffffffffffffffffffffffff",
            "amount_usd": 500000,
            "timestamp": (base_time - timedelta(days=2)).isoformat(),
            "from_label": "unknown",
            "to_label": "unknown"
        }
    ]


@pytest.mark.asyncio
async def test_label_address_known_entity(mock_database):
    """Test labeling a known exchange address"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    # Test with Binance-like address
    label = await clusterer.label_address("0xbinance1234567890")
    
    assert label["primary_label"] == "binance"
    assert label["category"] == "exchange"
    assert label["confidence"] == 0.8
    assert "keyword_match" in label["sources"]
    
    # Verify database was called
    mock_database.store_wallet_label.assert_called_once()


@pytest.mark.asyncio
async def test_label_address_unknown(mock_database):
    """Test labeling an unknown address"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    label = await clusterer.label_address("0x1234567890abcdef")
    
    assert label["primary_label"] == "unknown"
    assert label["category"] == "unknown"
    assert label["confidence"] == 0.0


@pytest.mark.asyncio
async def test_label_address_with_transaction_labels(mock_database):
    """Test labeling using transaction labels"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    label = await clusterer.label_address(
        "0x1234567890abcdef",
        from_label="binance",
        to_label=None
    )
    
    assert "related_to_binance" in label["primary_label"]
    assert label["category"] == "related"
    assert label["confidence"] == 0.5


@pytest.mark.asyncio
async def test_cluster_addresses_by_temporal_pattern(mock_database, sample_transactions):
    """Test temporal clustering of addresses"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    clusters = await clusterer.cluster_addresses_by_temporal_pattern(
        sample_transactions,
        window_hours=24
    )
    
    # Should have at least one cluster from recent transactions
    assert len(clusters) > 0
    
    # Clusters should contain sets of addresses
    for cluster_id, addresses in clusters.items():
        assert isinstance(addresses, set)
        assert len(addresses) >= clusterer.min_cluster_size


@pytest.mark.asyncio
async def test_cluster_addresses_by_value_pattern(mock_database, sample_transactions):
    """Test value-based clustering"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    clusters = await clusterer.cluster_addresses_by_value_pattern(sample_transactions)
    
    # Should group addresses with similar transaction amounts
    assert len(clusters) > 0
    
    # Verify cluster structure
    for cluster_id, addresses in clusters.items():
        assert isinstance(addresses, set)
        assert len(addresses) >= clusterer.min_cluster_size


@pytest.mark.asyncio
async def test_cluster_addresses_by_common_input(mock_database, sample_transactions):
    """Test common input heuristic clustering"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    clusters = await clusterer.cluster_addresses_by_common_input(sample_transactions)
    
    # Each cluster should represent addresses from same transaction
    for cluster_id, addresses in clusters.items():
        assert isinstance(addresses, set)


@pytest.mark.asyncio
async def test_merge_clusters(mock_database):
    """Test merging overlapping clusters"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    # Create overlapping clusters
    clusters1 = {
        "cluster1": {"0xaaaa", "0xbbbb", "0xcccc"},
        "cluster2": {"0xdddd", "0xeeee"}
    }
    
    clusters2 = {
        "cluster3": {"0xcccc", "0xdddd"},  # Overlaps with both cluster1 and cluster2
        "cluster4": {"0xffff", "0x1111"}
    }
    
    merged = await clusterer.merge_clusters([clusters1, clusters2])
    
    # Should merge overlapping clusters
    assert len(merged) <= len(clusters1) + len(clusters2)
    
    # All addresses should be present
    all_addresses = set()
    for addresses in merged.values():
        all_addresses.update(addresses)
    
    expected_addresses = {"0xaaaa", "0xbbbb", "0xcccc", "0xdddd", "0xeeee", "0xffff", "0x1111"}
    assert all_addresses == expected_addresses


@pytest.mark.asyncio
async def test_build_wallet_network(mock_database, sample_transactions):
    """Test building wallet network graph"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    network = await clusterer.build_wallet_network(sample_transactions)
    
    # Verify network structure
    assert "nodes" in network
    assert "edges" in network
    assert "clusters" in network
    
    # Should have nodes for all unique addresses
    unique_addresses = set()
    for tx in sample_transactions:
        if tx.get("from_address"):
            unique_addresses.add(tx["from_address"])
        if tx.get("to_address"):
            unique_addresses.add(tx["to_address"])
    
    assert len(network["nodes"]) == len(unique_addresses)
    
    # Should have edges for all transactions
    assert len(network["edges"]) == len(sample_transactions)
    
    # Verify node metrics
    for addr, node_data in network["nodes"].items():
        assert "tx_count" in node_data
        assert "total_volume" in node_data
        assert "label" in node_data


@pytest.mark.asyncio
async def test_process_whale_transactions_batch(mock_database, sample_transactions):
    """Test batch processing of whale transactions"""
    # Setup mock to return sample transactions
    mock_database.get_whale_transactions = AsyncMock(return_value=sample_transactions)
    
    clusterer = WhaleWalletClusterer(mock_database)
    
    results = await clusterer.process_whale_transactions_batch(hours=24, limit=1000)
    
    # Verify processing results
    assert results["status"] == "success"
    assert results["transactions_processed"] == len(sample_transactions)
    assert results["clusters_found"] > 0
    assert results["unique_addresses"] > 0
    
    # Verify database calls
    mock_database.get_whale_transactions.assert_called_once()
    # Should have stored clusters
    assert mock_database.store_wallet_cluster.call_count > 0


@pytest.mark.asyncio
async def test_process_whale_transactions_batch_no_data(mock_database):
    """Test batch processing with no transactions"""
    mock_database.get_whale_transactions = AsyncMock(return_value=[])
    
    clusterer = WhaleWalletClusterer(mock_database)
    
    results = await clusterer.process_whale_transactions_batch(hours=24, limit=1000)
    
    assert results["status"] == "no_data"
    assert results["transactions_processed"] == 0
    assert results["clusters_found"] == 0


@pytest.mark.asyncio
async def test_process_whale_transaction_streaming_new_cluster(mock_database):
    """Test streaming processing of single transaction (new cluster)"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    transaction = {
        "tx_hash": "0x1111",
        "from_address": "0xaaaa",
        "to_address": "0xbbbb",
        "amount_usd": 1000000,
        "timestamp": datetime.utcnow().isoformat(),
        "from_label": "unknown",
        "to_label": "binance"
    }
    
    result = await clusterer.process_whale_transaction_streaming(transaction)
    
    assert result["status"] == "processed"
    assert result["from_address"] == "0xaaaa"
    assert result["to_address"] == "0xbbbb"
    assert result["to_label"] == "binance"
    
    # Should have stored a new cluster
    mock_database.store_wallet_cluster.assert_called_once()


@pytest.mark.asyncio
async def test_process_whale_transaction_streaming_existing_cluster(mock_database):
    """Test streaming processing with existing cluster"""
    # Mock existing cluster
    mock_database.get_cluster_by_address = AsyncMock(return_value={
        "cluster_id": "cluster123",
        "addresses": ["0xaaaa"],
        "transaction_count": 5
    })
    
    clusterer = WhaleWalletClusterer(mock_database)
    
    transaction = {
        "tx_hash": "0x2222",
        "from_address": "0xaaaa",
        "to_address": "0xcccc",
        "amount_usd": 500000,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    result = await clusterer.process_whale_transaction_streaming(transaction)
    
    assert result["status"] == "processed"
    assert result["cluster_updated"] is True
    
    # Should have updated cluster
    mock_database.update_cluster_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_generate_cluster_id_deterministic(mock_database):
    """Test cluster ID generation is deterministic"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    addresses = {"0xaaaa", "0xbbbb", "0xcccc"}
    
    id1 = clusterer._generate_cluster_id(addresses)
    id2 = clusterer._generate_cluster_id(addresses)
    
    # Should generate same ID for same addresses
    assert id1 == id2
    
    # Should generate different ID for different addresses
    addresses2 = {"0xaaaa", "0xbbbb", "0xdddd"}
    id3 = clusterer._generate_cluster_id(addresses2)
    assert id1 != id3


@pytest.mark.asyncio
async def test_cluster_size_limits(mock_database, sample_transactions):
    """Test that clusters respect min/max size limits"""
    clusterer = WhaleWalletClusterer(mock_database)
    
    # Create transactions that would form very large cluster
    large_tx_set = []
    for i in range(100):
        large_tx_set.append({
            "tx_hash": f"0x{i:040x}",
            "from_address": f"0x{i:040x}",
            "to_address": "0xcommon",
            "amount_usd": 1000000,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # Process with common input clustering
    clusters = await clusterer.cluster_addresses_by_common_input(large_tx_set)
    
    # Merge and check size constraints
    merged = await clusterer.merge_clusters([clusters])
    
    for cluster_id, addresses in merged.items():
        assert len(addresses) >= clusterer.min_cluster_size
        assert len(addresses) <= clusterer.max_cluster_size


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
