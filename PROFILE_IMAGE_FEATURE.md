# Profile Image Upload Feature

## Overview

This feature allows users to upload and manage their profile images on the RMIT Connect platform. Users can upload profile photos that will be displayed across the application.

## Features Implemented

### 1. Database Schema

- Added `profile_image` field to the User model
- Stores the filename of the uploaded image
- Field is nullable (users can have no profile image)

### 2. Backend Implementation

- **Upload Route**: `/upload_profile_image` (POST)
  - Secure file upload handling
  - File type validation (PNG, JPG, JPEG, GIF, WEBP)
  - File size validation (max 5MB)
  - Image optimization (resize to max 800x800)
  - Secure filename generation with UUID
  - Rate limiting (10 uploads per 5 minutes)

### 3. Frontend Implementation

- **Dashboard**: Profile image display with upload overlay
- **Explore**: Profile images in user cards
- **Connections**: Profile images in connection cards
- **Profile View**: Profile images when viewing other users

### 4. Security Features

- CSRF protection on uploads
- File type validation
- File size limits
- Secure filename generation
- Rate limiting to prevent abuse
- Image processing for optimization

### 5. User Experience

- Hover overlay on profile image for upload
- Loading states during upload
- Success/error notifications
- Automatic image optimization
- Responsive design

## Technical Details

### File Storage

- Images stored in `static/uploads/` directory
- Filename format: `user_{user_id}_{uuid}.{extension}`
- Default image: `static/images/default-profile.png`

### Image Processing

- Automatic conversion to RGB if needed
- Resize to max 800x800 pixels
- Quality optimization (85%)
- Supports multiple formats

### Database Migration

- New `profile_image` column added to users table
- Existing users will use default image until they upload

## Usage

### For Users

1. Go to Dashboard
2. Click on profile image (hover to see "Change Photo" overlay)
3. Select image file (PNG, JPG, JPEG, GIF, WEBP)
4. Image will be uploaded and optimized automatically
5. Profile image will be updated across the platform

### For Developers

- Use `user.get_profile_image_url()` to get image URL
- Images are served from `/uploads/{filename}` route
- Default image served from `/static/images/default-profile.png`

## File Structure

```
static/
├── uploads/          # User uploaded images
│   └── user_*.jpg   # Profile images
├── images/
│   └── default-profile.png  # Default profile image
```

## API Endpoints

### POST /upload_profile_image

**Authentication**: Required (login_required)
**Rate Limit**: 10 requests per 5 minutes

**Request**:

- Content-Type: multipart/form-data
- Body: profile_image file

**Response**:

```json
{
  "success": true,
  "image_url": "/uploads/user_1_a1b2c3d4.jpg",
  "message": "Profile image updated successfully!"
}
```

**Error Response**:

```json
{
  "success": false,
  "error": "Error message"
}
```

## Security Considerations

- File type validation prevents malicious uploads
- File size limits prevent abuse
- Secure filename generation prevents path traversal
- Rate limiting prevents spam
- CSRF protection on all uploads
- Image processing removes potential metadata

## Performance Optimizations

- Images automatically resized to reasonable dimensions
- Quality optimization reduces file sizes
- Caching headers for uploaded images
- Lazy loading in templates
- Responsive image sizing

## Browser Support

- Modern browsers with File API support
- Fallback to default image for unsupported formats
- Progressive enhancement approach
