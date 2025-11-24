# Thumbnail URL Expiration Fix - Implementation Summary

## Problem
Presigned S3 URLs for video thumbnails were expiring after 1 hour, causing CORS-like errors when browsers tried to load expired URLs.

## Solution: On-Demand URL Generation (Option 2)

### Backend Changes

1. **New Lambda Function**: `extr-srv-api-refresh-thumbnail-urls`
   - Location: `/source/extraction_service/lambda/extr-srv-api-refresh-thumbnail-urls/`
   - Generates fresh presigned URLs on-demand
   - Input: Array of `{S3Bucket, S3Key}` objects
   - Output: Array of `{S3Bucket, S3Key, ThumbnailUrl}` objects

2. **Modified Lambda**: `extr-srv-api-search-tasks`
   - Now returns `S3Bucket` and `S3Key` instead of generating presigned URLs
   - Frontend calls refresh API to get URLs when needed

3. **New API Endpoint**: `POST /v1/extraction/video/refresh-thumbnail-urls`
   - Added to CDK stack in `extraction_service_stack.py`
   - Requires Cognito authentication
   - Uses S3 permissions only

### Frontend Changes

1. **New Utility**: `/source/frontend/web/src/resources/thumbnail-utils.js`
   - `refreshThumbnailUrls(items, service)` function
   - Batches thumbnail refresh requests
   - Maps refreshed URLs back to original items

2. **Updated Components**:
   - `frameSample/videoSearch.jsx` - Frame-based workflow
   - `videoClip/videoSearch.jsx` - Shot-based workflow  
   - `dataGeneration/dataMain.jsx` - Analytics dashboard

### How It Works

1. Backend API returns S3 bucket/key instead of presigned URLs
2. Frontend calls `refreshThumbnailUrls()` after receiving task list
3. Utility function batches all thumbnails and calls refresh API
4. Fresh presigned URLs (1 hour expiry) are generated on-demand
5. URLs are mapped back to original items and displayed

### Benefits

- ✅ URLs never stale - generated fresh when page loads
- ✅ Proper architecture - separation of concerns
- ✅ Minimal API calls - batched refresh requests
- ✅ No security changes - maintains presigned URL approach
- ✅ Works with temporary credentials

### Deployment

Run from deployment directory:
```bash
cd deployment
bash ./deploy.sh
```

Or for frontend-only updates:
```bash
cd deployment
bash ./update-frontend.sh
```

### Testing

1. Upload a video and wait for processing to complete
2. Leave browser tab open for >1 hour
3. Refresh the page
4. Thumbnails should load with fresh URLs (no CORS errors)
