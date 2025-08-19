# Scaleway Registry Purge

When you use a Scaleway container registry as part of a development workflow, the registry can quickly fill up with images or other artifacts that aren't needed after a short period. You might want to delete all tags that are older than a certain duration or match a specified name filter. To delete multiple artifacts quickly, this repository introduces the purge script you can run as an on-demand or scheduled Scaleway Serverless function.

## Features

- **Age-based deletion**: Delete tags older than 3 months (90 days)
- **Name-based deletion**: Delete tags matching a regex pattern
- **Namespace cleanup**: Delete empty namespaces after tag cleanup
- **Flexible configuration**: Enable/disable deletion criteria via environment variables
- **Detailed logging**: Track which tags and namespaces are deleted and why

## Environment Variables

### Required
- `REGION`: The Scaleway region where your registry is located (e.g., `fr-par`)
- `SCW_ACCESS_KEY`: Your Scaleway access key
- `SCW_SECRET_KEY`: Your Scaleway secret key

### Optional
- `DELETE_OLD_TAGS`: Enable/disable deletion of old tags (default: `true`)
  - Set to `true` to delete tags older than 3 months
  - Set to `false` to disable age-based deletion
- `TAG_NAME_PATTERN`: Regex pattern to match tag names for deletion
  - If not set, name-based deletion is disabled
  - Example: `^dev-.*` to delete all tags starting with "dev-"
  - Example: `.*-temp$` to delete all tags ending with "-temp"
- `DELETE_UNUSED_NAMESPACE`: Enable/disable deletion of empty namespaces (default: `false`)
  - Set to `true` to delete namespaces that contain no images after tag cleanup
  - Set to `false` to keep empty namespaces
- `NAMESPACE_ID`: Target a specific namespace (optional)
  - If set, operations will be limited to this namespace only
  - If not set, operations will apply to all namespaces
- `IMAGE_ID`: Target a specific image (optional)
  - If set, operations will be limited to this image only
  - Takes precedence over `NAMESPACE_ID` if both are set
  - If not set, operations will apply to all images (or namespace if `NAMESPACE_ID` is set)

## Usage Examples

**Note**: If both `NAMESPACE_ID` and `IMAGE_ID` are specified, `IMAGE_ID` takes precedence and the script will only process the specified image, regardless of the namespace setting.

### Delete only old tags (default behavior)
```bash
export REGION=fr-par
export DELETE_OLD_TAGS=true
```

### Delete only tags matching a pattern
```bash
export REGION=fr-par
export DELETE_OLD_TAGS=false
export TAG_NAME_PATTERN="^(dev|test)-.*"
```

### Delete both old tags AND tags matching a pattern
```bash
export REGION=fr-par
export DELETE_OLD_TAGS=true
export TAG_NAME_PATTERN=".*-temp$"
```

### Delete old tags and cleanup empty namespaces
```bash
export REGION=fr-par
export DELETE_OLD_TAGS=true
export DELETE_UNUSED_NAMESPACE=true
```

### Complete cleanup: tags by pattern + empty namespaces
```bash
export REGION=fr-par
export DELETE_OLD_TAGS=false
export TAG_NAME_PATTERN="^(dev|test)-.*"
export DELETE_UNUSED_NAMESPACE=true
```

### Target a specific namespace only
```bash
export REGION=fr-par
export NAMESPACE_ID=11111111-1111-1111-1111-111111111111
export DELETE_OLD_TAGS=true
export TAG_NAME_PATTERN=".*-temp$"
```

### Cleanup only a specific namespace (including empty namespace deletion)
```bash
export REGION=fr-par
export NAMESPACE_ID=11111111-1111-1111-1111-111111111111
export DELETE_OLD_TAGS=true
export DELETE_UNUSED_NAMESPACE=true
```

### Target a specific image only
```bash
export REGION=fr-par
export IMAGE_ID=22222222-2222-2222-2222-222222222222
export DELETE_OLD_TAGS=true
export TAG_NAME_PATTERN=".*-temp$"
```

### Target a specific image with name pattern matching
```bash
export REGION=fr-par
export IMAGE_ID=22222222-2222-2222-2222-222222222222
export DELETE_OLD_TAGS=false
export TAG_NAME_PATTERN="^(dev|test)-.*"
```

### Disable all deletion (dry run mode)
```bash
export REGION=fr-par
export DELETE_OLD_TAGS=false
# TAG_NAME_PATTERN not set
```

## Deployment

1. Install dependencies:
```bash
make install
```

2. Package the function:
```bash
make package
```

3. Deploy to Scaleway Functions (replace with your actual values):
```bash
# Create or update the function
scw function function deploy \
  --name registry-purge \
  --runtime python311 \
  --zip-file functions.zip \
  --handler "handlers/handlers.handle" \
  --env-vars REGION=fr-par \
  --env-vars DELETE_OLD_TAGS=true \
  --env-vars TAG_NAME_PATTERN="^dev-.*" \
  --env-vars DELETE_UNUSED_NAMESPACE=true \
  --env-vars NAMESPACE_ID=11111111-1111-1111-1111-111111111111 \
  --env-vars IMAGE_ID=22222222-2222-2222-2222-222222222222
```

## Response Format

The function returns a JSON response with detailed information:

```json
{
  "body": {
    "message": [
      {
        "tag_id": "tag-uuid",
        "tag_name": "dev-v1.0.0",
        "image_name": "my-app",
        "status": "deleted",
        "deletion_reasons": ["old", "name_match"],
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      },
      {
        "namespace_id": "namespace-uuid",
        "namespace_name": "old-project",
        "status": "deleted",
        "type": "namespace",
        "reason": "empty_namespace"
      }
    ],
    "summary": {
      "total_images_analyzed": 5,
      "total_tags_found": 10,
      "successfully_deleted": 8,
      "errors": 2,
      "namespaces_deleted": 1,
      "namespace_errors": 0,
      "criteria_used": {
        "delete_old_tags": true,
        "tag_name_pattern": "^dev-.*",
        "delete_unused_namespaces": true,
        "target_namespace_id": "11111111-1111-1111-1111-111111111111",
        "target_image_id": "22222222-2222-2222-2222-222222222222"
      }
    }
  },
  "statusCode": 200
}
```

## Security Notes

- The function uses Scaleway SDK authentication from environment or config file
- Ensure proper IAM permissions for registry operations
- Test with a small subset before running on production registries