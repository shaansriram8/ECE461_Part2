# DynamoDB Storage Migration

This document describes the migration from in-memory storage to DynamoDB for persistent artifact storage.

## Overview

The backend storage layer has been migrated from in-memory Python dictionaries to AWS DynamoDB. All storage operations now persist data to the `artifacts_metadata` DynamoDB table.

## Changes Made

### 1. New DynamoDB Storage Module
- **File**: `backend/storage/dynamodb.py`
- Implements all storage functions matching the previous memory storage interface
- Uses boto3 to interact with DynamoDB
- Handles serialization/deserialization of complex objects (Artifact, ModelRating)
- Includes proper exception handling for DynamoDB operations

### 2. Updated Storage Exports
- **File**: `backend/storage/__init__.py`
- Now exports DynamoDB storage functions instead of memory storage
- Maintains the same public API, so no changes needed in API routes

### 3. Updated API Routes
- **File**: `backend/api/routes/artifacts.py`
- All `memory.*` calls replaced with direct function imports
- No changes to API endpoints or behavior

### 4. Updated Rating Service
- **File**: `backend/services/rating_service.py`
- Updated to use new storage functions

### 5. Environment Variables
- **File**: `task-definition-mvp.json`
- Added `DDB_TABLE_NAME=artifacts_metadata`
- Added `AWS_REGION=us-east-2`

### 6. Test Script
- **File**: `scripts/test_dynamodb.py`
- Comprehensive test script for DynamoDB operations
- Can be run locally or inside container

## DynamoDB Table Schema

**Table Name**: `artifacts_metadata`  
**Primary Key**: `artifact_id` (String)  
**Region**: `us-east-2`  
**Capacity Mode**: On-demand

### Attributes
- `artifact_id` (String, PK) - Unique identifier
- `artifact_type` (String) - Type: "model", "dataset", or "code"
- `artifact` (String, JSON) - Serialized Artifact object
- `url` (String) - Artifact URL (for lookups)
- `name_normalized` (String) - Normalized name (for searches)
- `rating` (String, JSON, optional) - ModelRating for models
- `dataset_id` (String, optional) - Linked dataset ID
- `dataset_name` (String, optional) - Dataset name
- `dataset_url` (String, optional) - Dataset URL
- `code_id` (String, optional) - Linked code ID
- `code_name` (String, optional) - Code name
- `code_url` (String, optional) - Code URL

## IAM Permissions

The ECS task role `ecs-backend-access-role` has been configured with DynamoDB permissions:
- `dynamodb:GetItem`
- `dynamodb:PutItem`
- `dynamodb:UpdateItem`
- `dynamodb:DeleteItem`
- `dynamodb:Query`
- `dynamodb:Scan`

Resource restricted to: `arn:aws:dynamodb:us-east-2:978794836526:table/artifacts_metadata`

## Environment Variables

The following environment variables are required:

```bash
DDB_TABLE_NAME=artifacts_metadata
AWS_REGION=us-east-2
```

These are automatically set in the ECS task definition. For local testing, set them manually or use the test script.

## Testing

### Running the Test Script

```bash
# Set environment variables (if not already set)
export DDB_TABLE_NAME=artifacts_metadata
export AWS_REGION=us-east-2

# Run the test script
python scripts/test_dynamodb.py
```

The test script will:
1. Test basic CRUD operations
2. Test model artifacts with ratings
3. Test reset functionality

### Testing in Container

To test inside the ECS container:

```bash
# Connect to running container (if needed)
# Then run:
python scripts/test_dynamodb.py
```

The container will automatically use IAM role credentials from `ecs-backend-access-role`.

## Exception Handling

The DynamoDB module includes proper exception handling:

1. **ResourceNotFoundException**: Raised as `RuntimeError` if table doesn't exist
2. **ClientError**: Other DynamoDB errors are re-raised with context
3. **Missing Client**: If boto3 is unavailable, operations raise `RuntimeError`

All exceptions are caught and handled gracefully, preventing crashes.

## Migration Notes

- **No Data Migration Needed**: This is a fresh implementation. Existing in-memory data will not be migrated.
- **Backward Compatibility**: The storage interface remains the same, so API endpoints work without changes.
- **Performance**: DynamoDB operations are asynchronous-friendly and scale automatically with on-demand capacity.

## Next Steps

1. Deploy the updated task definition to ECS
2. Verify the container can connect to DynamoDB (check CloudWatch logs)
3. Test API endpoints to ensure data persists across container restarts
4. Monitor DynamoDB metrics in AWS Console

## Troubleshooting

### Table Not Found
- Verify table name matches `DDB_TABLE_NAME` environment variable
- Check table exists in `us-east-2` region
- Verify IAM permissions include DynamoDB access

### Permission Denied
- Verify `ecs-backend-access-role` has DynamoDB permissions
- Check IAM policy includes the correct table ARN
- Ensure task definition uses the correct task role

### Connection Issues
- Check VPC configuration allows DynamoDB access
- Verify security groups allow outbound HTTPS (port 443)
- Check CloudWatch logs for detailed error messages

