from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import imagehash
import io
import os
from supabase import create_client, Client

app = FastAPI(title="CloudGallery pHash API")

# Allow requests from the frontend (file:// or localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase Configuration
SUPABASE_URL = "https://ragirktlncfnvlomqsiw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJhZ2lya3RsbmNmbnZsb21xc2l3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc3MDYwNjYsImV4cCI6MjA5MzI4MjA2Nn0.0iNOQh_irF5QE2A9S5Ay-2mWAf-SBP7M6qdfwazEWD4"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Similarity threshold (Hamming distance <= 5 means it's visually very similar)
SIMILARITY_THRESHOLD = 5

def generate_phash(image_bytes: bytes) -> str:
    """
    Generates a perceptual hash (pHash) for an image.
    pHash focuses on low frequencies of an image to identify visual similarities
    even if the image has been resized, slightly cropped, or compressed.
    """
    img = Image.open(io.BytesIO(image_bytes))
    return str(imagehash.phash(img))

@app.post("/check-duplicate")
async def check_duplicate(
    file: UploadFile = File(...), 
    existing_hashes: str = Form("[]")
):
    import json
    try:
        # Read image bytes
        image_bytes = await file.read()
        
        # 1. Generate pHash for the incoming image
        new_hash_str = generate_phash(image_bytes)
        new_hash = imagehash.hex_to_hash(new_hash_str)
        
        # 2. Parse existing hashes from frontend
        hashes_list = json.loads(existing_hashes)
        
        closest_distance = None
        is_duplicate = False
        
        # 3. Compare using Hamming Distance
        for h_str in hashes_list:
            try:
                stored_hash = imagehash.hex_to_hash(h_str)
                distance = new_hash - stored_hash
                
                if closest_distance is None or distance < closest_distance:
                    closest_distance = distance
                    
                if distance <= SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    break
            except Exception:
                continue # Skip invalid hashes
                
        return {
            "is_duplicate": is_duplicate,
            "distance": closest_distance,
            "hash": new_hash_str
        }
        
    except Exception as e:
        return {"error": str(e), "is_duplicate": False, "hash": None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
