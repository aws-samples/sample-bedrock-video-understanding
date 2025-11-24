import { FetchPost } from "./data-provider";

/**
 * Refresh presigned URLs for thumbnails on-demand
 * @param {Array} items - Array of items with S3Bucket and S3Key properties
 * @param {string} service - Service name (e.g., "ExtrService", "NovaService", "TlabsService")
 * @returns {Promise<Array>} - Array of items with refreshed ThumbnailUrl
 */
export async function refreshThumbnailUrls(items, service = "ExtrService") {
    if (!items || items.length === 0) return items;
    
    const thumbnails = items
        .filter(item => item.S3Bucket && item.S3Key)
        .map(item => ({
            S3Bucket: item.S3Bucket,
            S3Key: item.S3Key
        }));
    
    if (thumbnails.length === 0) return items;
    
    try {
        const response = await FetchPost(
            "/extraction/video/refresh-thumbnail-urls",
            { Thumbnails: thumbnails },
            service
        );
        
        if (response.statusCode === 200) {
            const urlMap = {};
            JSON.parse(response.body).forEach(thumb => {
                const key = `${thumb.S3Bucket}/${thumb.S3Key}`;
                urlMap[key] = thumb.ThumbnailUrl;
            });
            
            return items.map(item => {
                if (item.S3Bucket && item.S3Key) {
                    const key = `${item.S3Bucket}/${item.S3Key}`;
                    return {
                        ...item,
                        ThumbnailUrl: urlMap[key] || item.ThumbnailUrl
                    };
                }
                return item;
            });
        }
    } catch (error) {
        console.error("Failed to refresh thumbnail URLs:", error);
    }
    
    return items;
}
