# Restaurant Search API Documentation

## Overview
The Restaurant Search API allows users to search for restaurants and food items with distance-based sorting. Results are automatically sorted by proximity to the user's location (nearest first).

## Base URL
```
http://localhost:8000/api/
```

## Authentication
Most endpoints require JWT token. Include in request header:
```
Authorization: Bearer <your_jwt_token>
```

---

## Endpoint: Search Restaurants

### Request

**URL:**
```
GET /restaurants/search/
```

**Method:** `GET`

**Authentication:** Not required (publicly accessible)

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| q | string | No | Search term (restaurant name or food name) |
| category | string | No | Filter by restaurant category name (case-insensitive) |
| city | string | No | Filter by city (case-insensitive) |
| user_lat | float | No* | User's latitude for distance calculation |
| user_lon | float | No* | User's longitude for distance calculation |
| page | integer | No | Page number (default: 1, 10 items per page) |

**\* Both `user_lat` and `user_lon` must be provided together for distance-based sorting. If only one is provided, it will be ignored.**

### Example Requests

#### 1. **Search by Food/Restaurant Name with Distance**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=biryani&user_lat=24.7136&user_lon=46.6753" \
  -H "Content-Type: application/json"
```

#### 2. **Search with Category Filter**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=pizza&category=Fast%20Food&user_lat=24.7136&user_lon=46.6753" \
  -H "Content-Type: application/json"
```

#### 3. **Search by City**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=burger&city=Riyadh&user_lat=24.7136&user_lon=46.6753" \
  -H "Content-Type: application/json"
```

#### 4. **Combined Filters with Pagination**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=biryani&category=Indian&city=Riyadh&user_lat=24.7136&user_lon=46.6753&page=2" \
  -H "Content-Type: application/json"
```

#### 5. **Search Without Distance (No Results Sorting)**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=pizza" \
  -H "Content-Type: application/json"
```

---

## Response Format

### Success Response (200 OK)

```json
{
  "success": true,
  "message": "Success",
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "brand_name": "Biryani Palace",
      "logo": "http://localhost:8000/media/restaurants/logos/2026/04/biryani_palace.png",
      "short_description": "Authentic Indian biryani restaurant",
      "city": "Riyadh",
      "short_address": "Olaya Street, Riyadh",
      "category_name": "Indian",
      "category_icon": "http://localhost:8000/media/restaurant_categories/icons/2026/04/indian.png",
      "distance": 2.45
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "brand_name": "Taj Mahal Restaurant",
      "logo": "http://localhost:8000/media/restaurants/logos/2026/04/taj_mahal.png",
      "short_description": "Fine dining Indian cuisine",
      "city": "Riyadh",
      "short_address": "Downtown Riyadh",
      "category_name": "Indian",
      "category_icon": "http://localhost:8000/media/restaurant_categories/icons/2026/04/indian.png",
      "distance": 3.82
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "brand_name": "Spice Kitchen",
      "logo": "http://localhost:8000/media/restaurants/logos/2026/04/spice_kitchen.png",
      "short_description": "Traditional Indian spices",
      "city": "Riyadh",
      "short_address": "King Fahd Road",
      "category_name": "Indian",
      "category_icon": "http://localhost:8000/media/restaurant_categories/icons/2026/04/indian.png",
      "distance": null
    }
  ],
  "meta": {
    "total": 25,
    "page": 1,
    "total_pages": 3,
    "has_next": true,
    "has_previous": false,
    "user_location": {
      "latitude": 24.7136,
      "longitude": 46.6753
    }
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| success | boolean | Request success status |
| message | string | Response message |
| data | array | List of restaurant results |
| data[].id | string (UUID) | Restaurant unique identifier |
| data[].brand_name | string | Restaurant name/brand |
| data[].logo | string (URL) | Absolute URL to restaurant logo |
| data[].short_description | string | Brief description of restaurant |
| data[].city | string | City where restaurant is located |
| data[].short_address | string | Short address of restaurant |
| data[].category_name | string | Restaurant category name |
| data[].category_icon | string (URL) | Absolute URL to category icon |
| data[].distance | float/null | Distance from user in kilometers (null if no user location provided or restaurant has no coordinates) |
| meta.total | integer | Total number of matching restaurants |
| meta.page | integer | Current page number |
| meta.total_pages | integer | Total number of pages |
| meta.has_next | boolean | Whether there's a next page |
| meta.has_previous | boolean | Whether there's a previous page |
| meta.user_location | object | User's location used for distance calculation (null if not provided) |

---

## Distance Calculation

### Algorithm
The API uses the **Haversine formula** to calculate straight-line distance between user location and restaurant location in kilometers.

### Distance Sorting Rules
1. **Restaurants with coordinates and user location provided:** Sorted by ascending distance (nearest first)
2. **Restaurants without coordinates:** Appear at the end of the list
3. **No user location provided:** Restaurants sorted by creation date (newest first), distance field is `null`

### Example Distance Sorting
```
User Location: 24.7136°N, 46.6753°E

Results (sorted by distance):
1. Biryani Palace          - 2.45 km away
2. Taj Mahal Restaurant    - 3.82 km away
3. Spice Kitchen           - 5.12 km away
4. Unknown Restaurant      - null (no coordinates set)
```

---

## Error Responses

### 400 Bad Request - Invalid Query Parameters

```json
{
  "success": false,
  "message": "Invalid input.",
  "errors": {
    "user_lat": ["Must provide both user_lat and user_lon"]
  }
}
```

### 400 Bad Request - Invalid Page Number

```json
{
  "success": false,
  "message": "Invalid page number.",
  "errors": {
    "page": ["Page must be a valid integer"]
  }
}
```

**Note:** Invalid page numbers default to page 1.

### 404 Not Found - No Results

```json
{
  "success": true,
  "message": "Success",
  "data": [],
  "meta": {
    "total": 0,
    "page": 1,
    "total_pages": 0,
    "has_next": false,
    "has_previous": false,
    "user_location": {
      "latitude": 24.7136,
      "longitude": 46.6753
    }
  }
}
```

### 500 Internal Server Error

```json
{
  "success": false,
  "message": "An unexpected error occurred.",
  "errors": {
    "detail": ["Server error details"]
  }
}
```

---

## Use Cases & Examples

### Use Case 1: Search Nearby Restaurants
**Scenario:** User wants to find all restaurants within walking distance of their current location.

**Request:**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?user_lat=24.7136&user_lon=46.6753" \
  -H "Authorization: Bearer <token>"
```

**Response:** All active restaurants sorted by distance.

---

### Use Case 2: Search for Specific Food with Distance
**Scenario:** User wants to find "pizza" restaurants closest to them.

**Request:**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=pizza&user_lat=24.7136&user_lon=46.6753" \
  -H "Authorization: Bearer <token>"
```

**Response:** Restaurants with "pizza" in name or menu items, sorted by distance.

---

### Use Case 3: Filter by Category and Distance
**Scenario:** User wants "Fast Food" restaurants in Riyadh sorted by proximity.

**Request:**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?category=Fast%20Food&city=Riyadh&user_lat=24.7136&user_lon=46.6753" \
  -H "Authorization: Bearer <token>"
```

**Response:** Fast food restaurants in Riyadh, sorted by distance from user.

---

### Use Case 4: Pagination with Search
**Scenario:** User wants to see page 2 of pizza restaurants (10 per page = items 11-20).

**Request:**
```bash
curl -X GET "http://localhost:8000/api/restaurants/search/?q=pizza&user_lat=24.7136&user_lon=46.6753&page=2" \
  -H "Authorization: Bearer <token>"
```

**Response:** Page 2 results (items 11-20), sorted by distance.

---

## Pagination

### How It Works
- **Page Size:** 10 restaurants per page
- **Default Page:** 1 (if not provided or invalid)
- **Invalid Pages:** Automatically default to page 1

### Example Pagination Flow
```
Total Results: 25 restaurants

Page 1: Items 1-10
  - Request: /restaurants/search/?page=1
  - has_next: true, has_previous: false

Page 2: Items 11-20
  - Request: /restaurants/search/?page=2
  - has_next: true, has_previous: true

Page 3: Items 21-25
  - Request: /restaurants/search/?page=3
  - has_next: false, has_previous: true
```

---

## Filtering

### Search Query (q parameter)
- Searches in **restaurant names** (brand_name, legal_name)
- Searches in **food item names** (MenuItem.name)
- Case-insensitive search
- Returns restaurants that match either criteria

**Examples:**
```
?q=biryani      → Finds "Biryani Palace" restaurant or biryani food items
?q=pizza        → Finds "Pizza Hut" restaurant or pizza food items
?q=sambhar      → Finds restaurants/food with "sambhar" in name
```

### Category Filter
- Filters by **restaurant category name**
- Case-insensitive partial match
- Used with search or standalone

**Examples:**
```
?category=Indian
?category=Fast%20Food
?category=Chinese
?q=biryani&category=Indian  → Biryani in Indian restaurants only
```

### City Filter
- Filters by **restaurant city**
- Case-insensitive partial match

**Examples:**
```
?city=Riyadh
?city=Jeddah
?q=pizza&city=Riyadh
```

---

## Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Successful search (may return 0 results) |
| 400 | Bad Request | Invalid query parameters |
| 401 | Unauthorized | Missing/invalid authentication token (if endpoint requires it) |
| 500 | Server Error | Internal server error |

---

## Rate Limiting

Currently **no rate limiting** is implemented. Production deployments should add rate limiting.

---

## Best Practices

### 1. **Always Provide User Location for Relevance**
```bash
# Good - Will sort by distance
?q=pizza&user_lat=24.7136&user_lon=46.6753

# Less optimal - No distance sorting
?q=pizza
```

### 2. **Use Specific Queries**
```bash
# Good - More specific
?q=biryani&category=Indian

# Less optimal - Too broad
?q=food
```

### 3. **Cache Results with Pagination**
```bash
# Fetch first page
?page=1

# Check meta.has_next and meta.total_pages
# Fetch next pages as needed
?page=2
```

### 4. **Handle Missing Distance Gracefully**
```javascript
// JavaScript example
const distance = restaurant.distance;
if (distance !== null) {
  console.log(`${distance} km away`);
} else {
  console.log('Location not available');
}
```

---

## Field Descriptions

### Distance Field
- **Type:** Float or null
- **Unit:** Kilometers (km)
- **Precision:** 2 decimal places
- **Null Condition:** When restaurant has no coordinates OR user location not provided

### Category Icon & Logo
- **Type:** Absolute URL (full HTTP URL)
- **Served By:** Django media server
- **Example:** `http://localhost:8000/media/restaurants/logos/2026/04/image.png`

---

## Testing the API

### Using cURL
```bash
# Basic search with distance
curl -X GET "http://localhost:8000/api/restaurants/search/?q=biryani&user_lat=24.7136&user_lon=46.6753"

# With authentication
curl -X GET "http://localhost:8000/api/restaurants/search/?q=pizza&user_lat=24.7136&user_lon=46.6753" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Using Postman
1. **Method:** GET
2. **URL:** `http://localhost:8000/api/restaurants/search/`
3. **Params Tab:**
   - Key: `q`, Value: `pizza`
   - Key: `user_lat`, Value: `24.7136`
   - Key: `user_lon`, Value: `46.6753`
   - Key: `page`, Value: `1`
4. **Headers Tab:**
   - Key: `Authorization`, Value: `Bearer <your_token>`
5. **Send**

### Using Python Requests
```python
import requests

url = "http://localhost:8000/api/restaurants/search/"
params = {
    "q": "biryani",
    "user_lat": 24.7136,
    "user_lon": 46.6753,
    "page": 1
}
headers = {
    "Authorization": "Bearer <your_token>"
}

response = requests.get(url, params=params, headers=headers)
print(response.json())
```

### Using JavaScript Fetch
```javascript
const params = new URLSearchParams({
  q: 'pizza',
  user_lat: 24.7136,
  user_lon: 46.6753,
  page: 1
});

fetch(`http://localhost:8000/api/restaurants/search/?${params}`, {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer <your_token>'
  }
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error('Error:', error));
```

---

## Troubleshooting

### Issue: Distance returning `null`
**Causes:**
- Restaurant has no latitude/longitude set
- User didn't provide their location (user_lat/user_lon)
- Only one of user_lat or user_lon provided

**Solution:**
- Admin must set restaurant coordinates in system
- Client must send both user_lat and user_lon parameters

### Issue: No results returned
**Causes:**
- No restaurants match the search query
- All matching restaurants are inactive
- Category/city filter too restrictive

**Solution:**
- Try broader search query (e.g., remove category filter)
- Check restaurant is_active status (may be inactive)
- Verify category name spelling

### Issue: Wrong distance values
**Causes:**
- Restaurant coordinates are incorrect
- User provided wrong coordinates
- Decimal precision issue

**Solution:**
- Verify restaurant latitude/longitude are correct (9 decimal places max)
- Verify user location accuracy
- Use known coordinates to test (e.g., Riyadh: 24.7136, 46.6753)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | April 8, 2026 | Initial release with distance-based search |

---

## Support

For issues or feature requests, contact the development team.

Last Updated: April 8, 2026
