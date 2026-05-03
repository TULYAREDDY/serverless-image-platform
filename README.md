# CloudGallery: Intelligent Serverless Image Processing Platform

## Overview

CloudGallery is a production-grade, full-stack image processing and hosting platform designed to provide secure, isolated, and highly optimized media management. 

**Problem Solved:** Traditional media upload systems frequently suffer from high storage redundancy due to duplicate image uploads, poor delivery performance from serving unoptimized assets, and security vulnerabilities related to multi-tenant data access. 

**Approach:** This architecture mitigates these issues by implementing a hybrid approach: a serverless edge architecture for immediate asset delivery and metadata storage, combined with a lightweight Python microservice dedicated to cryptographic and perceptual hashing. This decoupled design ensures that computationally expensive tasks (like Hamming distance evaluations for image similarity) do not block the frontend or overload the primary database, resulting in a highly scalable and fault-tolerant system.

## System Architecture

The system utilizes a decentralized flow to minimize server bottlenecks. The frontend communicates directly with the storage provider (Cloudinary) and the database (Supabase), delegating only specific compute-heavy operations to the Python backend.

```text
[ Client (Vanilla JS) ] 
       |       |
       |       +--(1) Auth & Metadata Sync---> [ Supabase (PostgreSQL + RLS) ]
       |                                                ^
       +-(2) Validate Hash-> [ Python backend (FastAPI) ] | (3) Fetch Hashes
       |                                                v
       +-(4) Direct Upload-> [ Cloudinary (Storage & CDN) ]
```

## Detailed Feature Implementation

### Authentication and Row-Level Security (RLS)
- **Implementation:** Authentication is handled via Supabase Auth (JWTs). PostgreSQL Row-Level Security (RLS) policies are bound directly to `auth.uid()`.
- **Reasoning:** Enforcing security at the database layer rather than the application layer guarantees data isolation. Even if the frontend application logic is bypassed, unauthorized data mutation or retrieval is impossible.
- **Trade-offs:** Requires precise SQL policy management and prevents the backend from utilizing anonymous connections for user-specific data retrieval without explicit JWT forwarding.

### Image Upload Pipeline
- **Implementation:** The client authenticates, generates a perceptual hash via the backend, and then utilizes a signed or predefined upload preset to send the binary payload directly to Cloudinary. Cloudinary returns a unique `public_id`, which the client then persists in Supabase alongside the `phash`.
- **Reasoning:** Direct-to-storage uploads bypass the backend, significantly reducing server bandwidth costs, memory consumption, and I/O blocking.
- **Trade-offs:** The client must be trusted to update the database after a successful Cloudinary upload, introducing a potential state mismatch if the database insertion fails post-upload.

### Perceptual Hashing (pHash) Duplicate Detection
- **Implementation:** The Python microservice uses `Pillow` and `imagehash` to generate a 64-bit perceptual hash. It computes the Hamming distance between the new image hash and the user's existing hashes.
- **Reasoning:** Unlike cryptographic hashes (MD5/SHA-256) which change entirely upon a single byte alteration, pHash evaluates low-frequency spatial structures. A Hamming distance threshold (e.g., `<= 5`) allows the system to detect visually identical images even if they have been resized, compressed, or slightly cropped.
- **Trade-offs:** pHash calculation requires loading the image into memory and decoding it, which is CPU-intensive compared to standard cryptographic hashing.

### Soft Delete and Versioning
- **Implementation:** Deletions toggle a `deleted` boolean flag rather than executing a `DELETE` SQL command. When a collision occurs on a non-deleted duplicate, the system can increment a `version` integer.
- **Reasoning:** Physical deletions destroy audit trails and complicate data recovery. Soft deletes maintain historical integrity and allow for straightforward implementation of "trash bin" recovery features.
- **Trade-offs:** Database size grows monotonically. Requires all `SELECT` queries to explicitly filter `WHERE deleted = false`, and periodic cron jobs to purge data beyond a retention policy.

### Thumbnail Optimization
- **Implementation:** Cloudinary URL transformation parameters (`w_600,q_auto,f_auto`) are applied at the CDN level before the image reaches the client.
- **Reasoning:** Serving raw, high-resolution uploads to a gallery view drastically degrades client performance and increases bandwidth costs. `q_auto` and `f_auto` allow the CDN to dynamically select the most efficient codec (e.g., WebP, AVIF) based on the requesting browser.
- **Trade-offs:** Requires reliance on vendor-specific URL structures.

## Data Model

The primary entity is the `images` table, structured to support multi-tenancy and version control.

- `id` (UUID, Primary Key): Unique identifier for the record.
- `user_id` (UUID, Foreign Key): References the `auth.users` table. Enforced by RLS.
- `public_id` (String): The Cloudinary asset identifier.
- `phash` (String): The 64-bit perceptual hash used for similarity matching.
- `deleted` (Boolean): Soft-delete flag (default: false).
- `version` (Integer): Incremental version number for iterative uploads.
- `created_at` (Timestamp): Record insertion time.

## Backend Design (pHash Service)

The backend is built utilizing FastAPI for high-throughput asynchronous request handling. 

- **Why Backend Implementation:** Generating a perceptual hash in the browser using WebAssembly or Canvas APIs is resource-intensive and prone to inconsistencies across different browser rendering engines. A Python backend standardizes the `Pillow` decoding process.
- **Hash Comparison Logic:** The service receives the image binary and a JSON array of the user's existing hashes. It computes the new pHash and iterates through the array, applying a subtraction operator (which natively calculates the Hamming distance in the `imagehash` library). 
- **Threshold Reasoning:** A Hamming distance of `0` denotes an exact pixel-for-pixel structural match. A threshold of `5` accommodates minor artifacting introduced by social media compression algorithms without triggering false positives on merely similar contexts.

## Security Considerations

- **RLS Enforcement:** The database is secure by default. An attacker obtaining the REST endpoint URL cannot iterate through integer IDs to scrape images due to RLS policies verifying the JWT signature.
- **API Validation:** The backend accepts localized comparisons. By forcing the frontend to fetch the user's hashes via the authenticated Supabase client and passing them to the backend, we bypass the need for complex backend impersonation while maintaining strict data access controls.
- **Frontend vs Backend Checks:** Frontend validation is superficial and can be bypassed. While the current duplicate check optimizes UX and prevents unnecessary network requests to Cloudinary, a secondary constraint at the database level is required for absolute integrity.

## Performance Considerations

- **CDN Offloading:** Image resizing and format conversion are entirely offloaded to Cloudinary's global CDN edge nodes, reducing Time to First Byte (TTFB).
- **Duplicate Prevention:** By halting the upload pipeline when a pHash collision is detected, the system saves bandwidth and storage costs associated with redundant binary blobs.
- **Query Efficiency:** The database fetches only the `phash` column array rather than entire row structures when preparing the payload for the comparison service, minimizing payload size.

## Setup Instructions

### Environment Variables
You must configure the following variables in your frontend deployment and backend environment:
```ini
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
CLOUD_NAME=your_cloudinary_cloud_name
UPLOAD_PRESET=your_cloudinary_unsigned_preset
```

### Backend Setup
1. Navigate to the backend directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the ASGI server:
   ```bash
   python -m uvicorn main:app --reload
   ```

### Frontend Setup
1. Serve the `index.html` file using any static file server (e.g., Live Server, Nginx, or Vercel).
2. Ensure the backend is running locally on port `8000` to allow the duplicate detection API to function.

## Future Improvements

1. **Approximate Nearest Neighbor (ANN) Search:** As the dataset scales, linear iteration over the hash array will become a bottleneck. Integrating an ANN search index (like FAISS or pgvector in Supabase) would allow for O(log N) similarity lookups.
2. **Serverless Migration:** The FastAPI backend can be containerized and deployed to a serverless platform (e.g., AWS Lambda, Google Cloud Run) to scale horizontally during high upload bursts.
3. **Webhook Integration:** Implement Cloudinary webhooks to independently verify upload success and automatically sync the metadata to Supabase, eliminating the client-side database insertion entirely.
