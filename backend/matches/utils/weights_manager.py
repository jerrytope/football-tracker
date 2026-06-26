import os
import boto3
import shutil
from urllib.parse import urlparse
from django.conf import settings

def get_weights_path():
    """
    Checks if YOLO weights exist locally.
    If not, downloads them from S3 (if configured).
    Returns the absolute path to the local weights file.
    """
    local_path = settings.YOLO_WEIGHTS_LOCAL_PATH
    
    # Resolve relative paths relative to base directory (or project root)
    if not os.path.isabs(local_path):
        # settings.BASE_DIR is backend/. Project root is backend/../
        project_root = settings.BASE_DIR.parent
        local_path = os.path.abspath(os.path.join(project_root, local_path))
        
    if os.path.exists(local_path):
        return local_path
        
    # Ensure directories exist
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    
    # Determine the fallback path in case S3 is not available/configured
    fallback_path = os.path.abspath(
        os.path.join(settings.BASE_DIR.parent, "cv_engine", "football_analysis_base", "models", "best.pt")
    )
    
    # Check if we should download from S3
    s3_path = settings.YOLO_WEIGHTS_S3_PATH
    if s3_path and s3_path.startswith("s3://") and settings.USE_S3:
        parsed_url = urlparse(s3_path)
        bucket_name = parsed_url.netloc
        key = parsed_url.path.lstrip("/")
        
        try:
            s3 = boto3.client("s3")
            s3.download_file(bucket_name, key, local_path)
            return local_path
        except Exception as e:
            # Fall back to development best.pt if S3 fails
            if os.path.exists(fallback_path):
                shutil.copy2(fallback_path, local_path)
                return local_path
            raise RuntimeError(f"Failed to download YOLO weights from S3: {e}")
            
    # Dev Fallback if S3 is not used/configured
    if os.path.exists(fallback_path):
        shutil.copy2(fallback_path, local_path)
        return local_path
        
    raise FileNotFoundError(
        f"YOLO weights not found at {local_path} and fallback at {fallback_path} does not exist."
    )
