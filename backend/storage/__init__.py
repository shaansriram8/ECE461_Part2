"""Storage module for artifact persistence.

This module exports the storage implementation. Currently uses DynamoDB
for persistent storage in AWS, but can be switched to memory for local
development if needed.
"""

from backend.storage import dynamodb

# Export all storage functions from dynamodb module
from backend.storage.dynamodb import (
    artifact_exists,
    delete_artifact,
    find_code_by_name,
    find_dataset_by_name,
    generate_artifact_id,
    get_artifact,
    get_model_rating,
    list_metadata,
    query_artifacts,
    reset,
    save_artifact,
    save_model_rating,
)

__all__ = [
    "artifact_exists",
    "delete_artifact",
    "find_code_by_name",
    "find_dataset_by_name",
    "generate_artifact_id",
    "get_artifact",
    "get_model_rating",
    "list_metadata",
    "query_artifacts",
    "reset",
    "save_artifact",
    "save_model_rating",
]

