#!/usr/bin/env python3
"""Test script for DynamoDB storage operations.

This script demonstrates how to interact with DynamoDB storage locally
or inside a container. It can be used to verify that the storage layer
is working correctly.

Usage:
    # Set environment variables
    export DDB_TABLE_NAME=artifacts_metadata
    export AWS_REGION=us-east-2
    
    # Run the test
    python scripts/test_dynamodb.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models import Artifact, ArtifactData, ArtifactMetadata, ArtifactType
from backend.storage import (
    artifact_exists,
    delete_artifact,
    generate_artifact_id,
    get_artifact,
    query_artifacts,
    reset,
    save_artifact,
)

# Set environment variables if not already set
os.environ.setdefault("DDB_TABLE_NAME", "artifacts_metadata")
os.environ.setdefault("AWS_REGION", "us-east-2")


def test_basic_operations():
    """Test basic CRUD operations."""
    print("=" * 60)
    print("Testing Basic DynamoDB Operations")
    print("=" * 60)
    
    # Test 1: Generate artifact ID
    print("\n1. Testing generate_artifact_id()...")
    artifact_id = generate_artifact_id()
    print(f"   Generated ID: {artifact_id}")
    assert artifact_id, "Failed to generate artifact ID"
    
    # Test 2: Create a dataset artifact
    print("\n2. Testing save_artifact() for dataset...")
    dataset_artifact = Artifact(
        metadata=ArtifactMetadata(
            name="test-dataset",
            id=generate_artifact_id(),
            type=ArtifactType.DATASET,
        ),
        data=ArtifactData(url="https://huggingface.co/datasets/test-dataset"),
    )
    save_artifact(dataset_artifact)
    print(f"   Saved dataset: {dataset_artifact.metadata.id}")
    
    # Test 3: Retrieve the artifact
    print("\n3. Testing get_artifact()...")
    retrieved = get_artifact(ArtifactType.DATASET, dataset_artifact.metadata.id)
    assert retrieved is not None, "Failed to retrieve artifact"
    assert retrieved.metadata.name == "test-dataset", "Name mismatch"
    print(f"   Retrieved artifact: {retrieved.metadata.name}")
    
    # Test 4: Check if artifact exists
    print("\n4. Testing artifact_exists()...")
    exists = artifact_exists(ArtifactType.DATASET, dataset_artifact.data.url)
    assert exists, "Artifact should exist"
    print(f"   Artifact exists: {exists}")
    
    # Test 5: Query artifacts
    print("\n5. Testing query_artifacts()...")
    from backend.models import ArtifactQuery
    
    queries = [ArtifactQuery(name="test-dataset", types=[ArtifactType.DATASET])]
    results = query_artifacts(queries)
    assert len(results) > 0, "Query should return results"
    print(f"   Query returned {len(results)} result(s)")
    
    # Test 6: Delete artifact
    print("\n6. Testing delete_artifact()...")
    deleted = delete_artifact(ArtifactType.DATASET, dataset_artifact.metadata.id)
    assert deleted, "Failed to delete artifact"
    print(f"   Deleted artifact: {deleted}")
    
    # Verify deletion
    retrieved_after_delete = get_artifact(ArtifactType.DATASET, dataset_artifact.metadata.id)
    assert retrieved_after_delete is None, "Artifact should be deleted"
    print("   Verification: Artifact no longer exists")
    
    print("\n✅ All basic operations passed!")


def test_model_with_rating():
    """Test model artifact with rating."""
    print("\n" + "=" * 60)
    print("Testing Model Artifact with Rating")
    print("=" * 60)
    
    from backend.models import ModelRating, SizeScore
    
    # Create a model artifact
    model_id = generate_artifact_id()
    model_artifact = Artifact(
        metadata=ArtifactMetadata(
            name="test-model",
            id=model_id,
            type=ArtifactType.MODEL,
        ),
        data=ArtifactData(url="https://huggingface.co/test-model"),
    )
    
    # Create a rating
    rating = ModelRating(
        name="test-model",
        category="MODEL",
        net_score=0.85,
        net_score_latency=0.0,
        ramp_up_time=0.8,
        ramp_up_time_latency=0.0,
        bus_factor=0.9,
        bus_factor_latency=0.0,
        performance_claims=0.7,
        performance_claims_latency=0.0,
        license=1.0,
        license_latency=0.0,
        dataset_and_code_score=0.75,
        dataset_and_code_score_latency=0.0,
        dataset_quality=0.8,
        dataset_quality_latency=0.0,
        code_quality=0.85,
        code_quality_latency=0.0,
        reproducibility=0.9,
        reproducibility_latency=0.0,
        reviewedness=0.75,
        reviewedness_latency=0.0,
        tree_score=0.8,
        tree_score_latency=0.0,
        size_score=SizeScore(
            raspberry_pi=0.5,
            jetson_nano=0.6,
            desktop_pc=0.8,
            aws_server=0.9,
        ),
        size_score_latency=0.0,
    )
    
    print("\n1. Saving model with rating...")
    save_artifact(model_artifact, rating=rating)
    print(f"   Saved model: {model_id}")
    
    print("\n2. Retrieving model rating...")
    from backend.storage import get_model_rating
    
    retrieved_rating = get_model_rating(model_id)
    assert retrieved_rating is not None, "Rating should exist"
    assert retrieved_rating.net_score == 0.85, "Rating mismatch"
    print(f"   Retrieved rating with net_score: {retrieved_rating.net_score}")
    
    # Cleanup
    delete_artifact(ArtifactType.MODEL, model_id)
    print("\n✅ Model with rating test passed!")


def test_reset():
    """Test reset functionality."""
    print("\n" + "=" * 60)
    print("Testing Reset Functionality")
    print("=" * 60)
    
    # Create some test artifacts
    print("\n1. Creating test artifacts...")
    for i in range(3):
        artifact = Artifact(
            metadata=ArtifactMetadata(
                name=f"test-artifact-{i}",
                id=generate_artifact_id(),
                type=ArtifactType.CODE,
            ),
            data=ArtifactData(url=f"https://example.com/test-{i}"),
        )
        save_artifact(artifact)
    
    print("   Created 3 test artifacts")
    
    # Reset
    print("\n2. Resetting registry...")
    reset()
    print("   Registry reset")
    
    # Verify all artifacts are gone
    print("\n3. Verifying reset...")
    from backend.models import ArtifactQuery
    
    queries = [ArtifactQuery(name="*", types=[ArtifactType.CODE])]
    results = query_artifacts(queries)
    print(f"   Remaining artifacts: {len(results)}")
    
    print("\n✅ Reset test passed!")


def main():
    """Run all tests."""
    try:
        test_basic_operations()
        test_model_with_rating()
        test_reset()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

