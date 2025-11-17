from __future__ import annotations

import json
import os
import uuid
from typing import Dict, Iterable, List, Optional, cast

import boto3
from botocore.exceptions import ClientError

from backend.models import (Artifact, ArtifactData, ArtifactID,
                            ArtifactMetadata, ArtifactQuery, ArtifactType,
                            ModelRating)
from backend.storage.records import CodeRecord, DatasetRecord, ModelRecord

# ---------------------------------------------------------------------------
# DynamoDB Configuration
# ---------------------------------------------------------------------------

TABLE_NAME = os.getenv("DDB_TABLE_NAME", "artifacts_metadata")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

# Initialize DynamoDB client
try:
    dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)
except Exception as e:
    # Fallback for local development or when boto3 is not available
    dynamodb = None


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def generate_artifact_id() -> ArtifactID:
    """Generate a unique artifact ID."""
    return str(uuid.uuid4())


def _normalized(name: Optional[str]) -> Optional[str]:
    """Normalize a name for comparison."""
    return name.strip().lower() if isinstance(name, str) else None


def _serialize_artifact(artifact: Artifact) -> Dict:
    """Serialize an Artifact to a dictionary for DynamoDB storage."""
    return {
        "metadata": {
            "name": artifact.metadata.name,
            "id": artifact.metadata.id,
            "type": artifact.metadata.type.value,
        },
        "data": {
            "url": artifact.data.url,
            "download_url": artifact.data.download_url,
        },
    }


def _deserialize_artifact(item: Dict) -> Artifact:
    """Deserialize a DynamoDB item to an Artifact."""
    artifact_str = item.get("artifact", {}).get("S", "{}")
    if isinstance(artifact_str, str):
        artifact_dict = json.loads(artifact_str)
    else:
        artifact_dict = artifact_str
    
    metadata_dict = artifact_dict.get("metadata", {})
    data_dict = artifact_dict.get("data", {})
    
    return Artifact(
        metadata=ArtifactMetadata(
            name=metadata_dict.get("name", ""),
            id=metadata_dict.get("id", ""),
            type=ArtifactType(metadata_dict.get("type", "model")),
        ),
        data=ArtifactData(
            url=data_dict.get("url", ""),
            download_url=data_dict.get("download_url"),
        ),
    )


def _serialize_rating(rating: Optional[ModelRating]) -> Optional[Dict]:
    """Serialize a ModelRating to a dictionary for DynamoDB storage."""
    if not rating:
        return None
    return rating.model_dump()


def _deserialize_rating(item: Dict) -> Optional[ModelRating]:
    """Deserialize a DynamoDB item to a ModelRating."""
    rating_data = item.get("rating")
    if not rating_data:
        return None
    
    # Handle both DynamoDB format and direct dict
    if isinstance(rating_data, dict):
        if "M" in rating_data:  # DynamoDB Map format
            rating_dict = {k: v.get("S") if "S" in v else v.get("N") if "N" in v else v for k, v in rating_data["M"].items()}
        else:
            rating_dict = rating_data
    else:
        return None
    
    # Handle nested size_score
    if "size_score" in rating_dict:
        size_score = rating_dict["size_score"]
        if isinstance(size_score, dict) and "M" in size_score:
            rating_dict["size_score"] = {
                k: float(v.get("N", 0)) if "N" in v else v.get("S", "")
                for k, v in size_score["M"].items()
            }
        elif isinstance(size_score, str):
            rating_dict["size_score"] = json.loads(size_score)
    
    try:
        return ModelRating(**rating_dict)
    except Exception:
        return None


def _get_item(artifact_id: ArtifactID) -> Optional[Dict]:
    """Get an item from DynamoDB by artifact_id."""
    if not dynamodb:
        raise RuntimeError("DynamoDB client not initialized")
    
    try:
        response = dynamodb.get_item(
            TableName=TABLE_NAME,
            Key={"artifact_id": {"S": artifact_id}},
        )
        if "Item" in response:
            return response["Item"]
        return None
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise RuntimeError(f"DynamoDB table {TABLE_NAME} not found") from e
        raise


def _put_item(item: Dict) -> None:
    """Put an item into DynamoDB."""
    if not dynamodb:
        raise RuntimeError("DynamoDB client not initialized")
    
    try:
        dynamodb.put_item(TableName=TABLE_NAME, Item=item)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise RuntimeError(f"DynamoDB table {TABLE_NAME} not found") from e
        raise


def _delete_item(artifact_id: ArtifactID) -> None:
    """Delete an item from DynamoDB."""
    if not dynamodb:
        raise RuntimeError("DynamoDB client not initialized")
    
    try:
        dynamodb.delete_item(
            TableName=TABLE_NAME,
            Key={"artifact_id": {"S": artifact_id}},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise RuntimeError(f"DynamoDB table {TABLE_NAME} not found") from e
        raise


def _scan_table() -> List[Dict]:
    """Scan the entire DynamoDB table."""
    if not dynamodb:
        raise RuntimeError("DynamoDB client not initialized")
    
    try:
        items = []
        response = dynamodb.scan(TableName=TABLE_NAME)
        items.extend(response.get("Items", []))
        
        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = dynamodb.scan(
                TableName=TABLE_NAME,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        
        return items
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise RuntimeError(f"DynamoDB table {TABLE_NAME} not found") from e
        raise


def _find_by_url(artifact_type: ArtifactType, url: str) -> Optional[ArtifactID]:
    """Find an artifact by URL using scan (since we don't have a GSI for URL)."""
    items = _scan_table()
    for item in items:
        artifact_type_str = item.get("artifact_type", {}).get("S", "")
        if artifact_type_str == artifact_type.value:
            # Check URL attribute first (faster)
            item_url = item.get("url", {}).get("S", "")
            if item_url == url:
                return item.get("artifact_id", {}).get("S")
    return None


def _link_dataset_code(model_record: ModelRecord, all_items: List[Dict]) -> None:
    """Link dataset and code to a model record by name matching."""
    dataset_name = _normalized(model_record.dataset_name)
    if model_record.dataset_id is None and dataset_name:
        for item in all_items:
            artifact_type = item.get("artifact_type", {}).get("S", "")
            if artifact_type == ArtifactType.DATASET.value:
                artifact_data = json.loads(item.get("artifact", {}).get("S", "{}"))
                if isinstance(artifact_data, str):
                    artifact_data = json.loads(artifact_data)
                item_name = artifact_data.get("metadata", {}).get("name", "")
                if _normalized(item_name) == dataset_name:
                    model_record.dataset_id = item.get("artifact_id", {}).get("S")
                    model_record.dataset_url = artifact_data.get("data", {}).get("url", "")
                    break

    code_name = _normalized(model_record.code_name)
    if model_record.code_id is None and code_name:
        for item in all_items:
            artifact_type = item.get("artifact_type", {}).get("S", "")
            if artifact_type == ArtifactType.CODE.value:
                artifact_data = json.loads(item.get("artifact", {}).get("S", "{}"))
                if isinstance(artifact_data, str):
                    artifact_data = json.loads(artifact_data)
                item_name = artifact_data.get("metadata", {}).get("name", "")
                if _normalized(item_name) == code_name:
                    model_record.code_id = item.get("artifact_id", {}).get("S")
                    model_record.code_url = artifact_data.get("data", {}).get("url", "")
                    break


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def save_artifact(
    artifact: Artifact,
    *,
    rating: Optional[ModelRating] = None,
    dataset_name: Optional[str] = None,
    dataset_url: Optional[str] = None,
    code_name: Optional[str] = None,
    code_url: Optional[str] = None,
) -> Artifact:
    """Insert or update an artifact entry in DynamoDB."""
    artifact_dict = _serialize_artifact(artifact)
    name_normalized = _normalized(artifact.metadata.name)
    
    # Build the DynamoDB item
    item = {
        "artifact_id": {"S": artifact.metadata.id},
        "artifact_type": {"S": artifact.metadata.type.value},
        "artifact": {"S": json.dumps(artifact_dict)},
        "url": {"S": artifact.data.url},
        "name_normalized": {"S": name_normalized or ""},
    }
    
    if artifact.metadata.type == ArtifactType.MODEL:
        # Get existing item to preserve relationships if updating
        existing_item = _get_item(artifact.metadata.id)
        dataset_id = None
        code_id = None
        if existing_item:
            # Preserve existing relationships if not provided
            if not dataset_name:
                dataset_id = existing_item.get("dataset_id", {}).get("S") if "dataset_id" in existing_item else None
            if not code_name:
                code_id = existing_item.get("code_id", {}).get("S") if "code_id" in existing_item else None
        
        # Update with provided values
        if dataset_name:
            item["dataset_name"] = {"S": dataset_name}
        if dataset_url:
            item["dataset_url"] = {"S": dataset_url}
        if code_name:
            item["code_name"] = {"S": code_name}
        if code_url:
            item["code_url"] = {"S": code_url}
        
        # Try to link by name
        all_items = _scan_table()
        model_record = ModelRecord(
            artifact=artifact,
            rating=rating,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            dataset_url=dataset_url,
            code_id=code_id,
            code_name=code_name,
            code_url=code_url,
        )
        _link_dataset_code(model_record, all_items)
        
        # Update item with linked IDs
        if model_record.dataset_id:
            item["dataset_id"] = {"S": model_record.dataset_id}
        if model_record.code_id:
            item["code_id"] = {"S": model_record.code_id}
        
        # Store rating if provided
        if rating:
            rating_dict = _serialize_rating(rating)
            item["rating"] = {"S": json.dumps(rating_dict)}
    elif artifact.metadata.type == ArtifactType.DATASET:
        # When a dataset is saved, update any models that reference it by name
        all_items = _scan_table()
        for model_item in all_items:
            if model_item.get("artifact_type", {}).get("S") == ArtifactType.MODEL.value:
                model_dataset_name = model_item.get("dataset_name", {}).get("S", "")
                if _normalized(model_dataset_name) == name_normalized:
                    model_item["dataset_id"] = {"S": artifact.metadata.id}
                    model_item["dataset_url"] = {"S": artifact.data.url}
                    _put_item(model_item)
    elif artifact.metadata.type == ArtifactType.CODE:
        # When code is saved, update any models that reference it by name
        all_items = _scan_table()
        for model_item in all_items:
            if model_item.get("artifact_type", {}).get("S") == ArtifactType.MODEL.value:
                model_code_name = model_item.get("code_name", {}).get("S", "")
                if _normalized(model_code_name) == name_normalized:
                    model_item["code_id"] = {"S": artifact.metadata.id}
                    model_item["code_url"] = {"S": artifact.data.url}
                    _put_item(model_item)
    
    _put_item(item)
    return artifact


def get_artifact(artifact_type: ArtifactType, artifact_id: ArtifactID) -> Optional[Artifact]:
    """Get an artifact by type and ID."""
    item = _get_item(artifact_id)
    if not item:
        return None
    
    # Verify the artifact type matches
    stored_type = item.get("artifact_type", {}).get("S", "")
    if stored_type != artifact_type.value:
        return None
    
    return _deserialize_artifact(item)


def delete_artifact(artifact_type: ArtifactType, artifact_id: ArtifactID) -> bool:
    """Delete an artifact from DynamoDB."""
    item = _get_item(artifact_id)
    if not item:
        return False
    
    # Verify the artifact type matches
    stored_type = item.get("artifact_type", {}).get("S", "")
    if stored_type != artifact_type.value:
        return False
    
    # If deleting a dataset or code, update related models
    if artifact_type == ArtifactType.DATASET:
        all_items = _scan_table()
        for model_item in all_items:
            if model_item.get("artifact_type", {}).get("S") == ArtifactType.MODEL.value:
                model_dataset_id = model_item.get("dataset_id", {}).get("S", "")
                if model_dataset_id == artifact_id:
                    model_item.pop("dataset_id", None)
                    model_item.pop("dataset_url", None)
                    _put_item(model_item)
    elif artifact_type == ArtifactType.CODE:
        all_items = _scan_table()
        for model_item in all_items:
            if model_item.get("artifact_type", {}).get("S") == ArtifactType.MODEL.value:
                model_code_id = model_item.get("code_id", {}).get("S", "")
                if model_code_id == artifact_id:
                    model_item.pop("code_id", None)
                    model_item.pop("code_url", None)
                    _put_item(model_item)
    
    _delete_item(artifact_id)
    return True


def list_metadata(artifact_type: ArtifactType) -> List[ArtifactMetadata]:
    """List all metadata for a given artifact type."""
    items = _scan_table()
    metadata_list = []
    for item in items:
        stored_type = item.get("artifact_type", {}).get("S", "")
        if stored_type == artifact_type.value:
            artifact = _deserialize_artifact(item)
            metadata_list.append(artifact.metadata)
    return metadata_list


def query_artifacts(queries: Iterable[ArtifactQuery]) -> List[ArtifactMetadata]:
    """Query artifacts by name across types."""
    items = _scan_table()
    results: Dict[str, ArtifactMetadata] = {}
    
    for query in queries:
        types = query.types or [ArtifactType.MODEL, ArtifactType.DATASET, ArtifactType.CODE]
        for artifact_type in types:
            for item in items:
                stored_type = item.get("artifact_type", {}).get("S", "")
                if stored_type == artifact_type.value:
                    artifact = _deserialize_artifact(item)
                    metadata = artifact.metadata
                    
                    # Match by name (exact match except "*")
                    if query.name == "*" or query.name.lower() == metadata.name.lower():
                        results[f"{metadata.type}:{metadata.id}"] = metadata
    
    return list(results.values())


def reset() -> None:
    """Reset the registry by deleting all items."""
    items = _scan_table()
    for item in items:
        artifact_id = item.get("artifact_id", {}).get("S")
        if artifact_id:
            _delete_item(artifact_id)


# ---------------------------------------------------------------------------
# Additional helpers for registration workflow
# ---------------------------------------------------------------------------

def artifact_exists(artifact_type: ArtifactType, url: str) -> bool:
    """Check if an artifact exists by URL."""
    return _find_by_url(artifact_type, url) is not None


def save_model_rating(artifact_id: ArtifactID, rating: ModelRating) -> None:
    """Save a model rating."""
    item = _get_item(artifact_id)
    if not item:
        return
    
    stored_type = item.get("artifact_type", {}).get("S", "")
    if stored_type != ArtifactType.MODEL.value:
        return
    
    rating_dict = _serialize_rating(rating)
    item["rating"] = {"S": json.dumps(rating_dict)}
    _put_item(item)


def get_model_rating(artifact_id: ArtifactID) -> Optional[ModelRating]:
    """Get a model rating."""
    item = _get_item(artifact_id)
    if not item:
        return None
    
    stored_type = item.get("artifact_type", {}).get("S", "")
    if stored_type != ArtifactType.MODEL.value:
        return None
    
    return _deserialize_rating(item)


def find_dataset_by_name(name: str) -> Optional[DatasetRecord]:
    """Find a dataset by normalized name."""
    normalized = _normalized(name)
    items = _scan_table()
    for item in items:
        stored_type = item.get("artifact_type", {}).get("S", "")
        if stored_type == ArtifactType.DATASET.value:
            artifact = _deserialize_artifact(item)
            if _normalized(artifact.metadata.name) == normalized:
                return DatasetRecord(artifact=artifact)
    return None


def find_code_by_name(name: str) -> Optional[CodeRecord]:
    """Find code by normalized name."""
    normalized = _normalized(name)
    items = _scan_table()
    for item in items:
        stored_type = item.get("artifact_type", {}).get("S", "")
        if stored_type == ArtifactType.CODE.value:
            artifact = _deserialize_artifact(item)
            if _normalized(artifact.metadata.name) == normalized:
                return CodeRecord(artifact=artifact)
    return None

