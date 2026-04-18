# Employee Order List & Details API Documentation

## Overview
Employees can view orders specific to their branch and access detailed information about individual orders. The API provides role-based access control where employees only see orders from their assigned branch.

## Base URL
```
http://localhost:8000/api/
```

## Authentication
All endpoints require JWT authentication. Include in request header:
```
Authorization: Bearer <your_jwt_token>
```

---

## Endpoint 1: Employee Order List

### Request

**URL:**
```
GET /staff/orders/
```

**Method:** `GET`

**Authentication:** Required (Authenticated users only)

### Access Control
- **Employee**: Can view orders from their assigned branch only
- **Owner**: Can view all orders from their restaurant's branches
- **Admin**: Can view all orders in the system

### Query Parameters

| Parameter | Type | Required | Default | Max | Description |
|-----------|------|----------|---------|-----|-------------|
| `status` | string | No | - | - | Filter orders by status (pending, preparing, ready, delivered, cancelled, accepted) |
| `page` | integer | No | 1 | - | Page number for pagination |
| `page_size` | integer | No | 20 | 100 | Number of orders per page |

### Example Requests

#### 1. **Get all pending orders for employee's branch**
```bash
curl -X GET "http://localhost:8000/api/staff/orders/?status=pending" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

#### 2. **Get orders with pagination (Page 2, 10 items per page)**
```bash
curl -X GET "http://localhost:8000/api/staff/orders/?page=2&page_size=10" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

#### 3. **Get preparing orders with pagination**
```bash
curl -X GET "http://localhost:8000/api/staff/orders/?status=preparing&page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### Success Response (200 OK)

```json
{
  "success": true,
  "message": null,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "order_number": "ORD-5432",
      "status": "pending",
      "payment_method": "hand_cash",
      "payment_status": "pending",
      "total": "150.00",
      "pickup_time": "15 minutes",
      "note": "No onions please",
      "branch_name": "Downtown Branch",
      "restaurant_name": "Pizza Palace",
      "item_count": 3,
      "car": {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "car_model": "Toyota Camry",
        "plate_number": "ABC-1234",
        "car_color": "#CCCCCC"
      },
      "created_at": "2026-04-18T10:30:00Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "order_number": "ORD-5431",
      "status": "preparing",
      "payment_method": "stripe",
      "payment_status": "paid",
      "total": "200.50",
      "pickup_time": "20 minutes",
      "note": "",
      "branch_name": "Downtown Branch",
      "restaurant_name": "Pizza Palace",
      "item_count": 2,
      "car": {
        "id": "550e8400-e29b-41d4-a716-446655440003",
        "car_model": "Honda Civic",
        "plate_number": "XYZ-5678",
        "car_color": "#FF0000"
      },
      "created_at": "2026-04-18T10:15:00Z"
    }
  ],
  "meta": {
    "total": 45,
    "page": 1,
    "page_size": 20,
    "pages": 3
  }
}
```

### Error Responses

#### 404 - Employee Profile Not Found
```json
{
  "success": false,
  "message": "Employee profile not found.",
  "data": null
}
```

#### 403 - Unauthorized
```json
{
  "success": false,
  "message": "Unauthorized.",
  "data": null
}
```

#### 401 - Not Authenticated
```json
{
  "success": false,
  "message": "Authentication credentials were not provided.",
  "data": null
}
```

---

## Endpoint 2: Order Details

### Request

**URL:**
```
GET /staff/orders/{order_id}/
```

**Method:** `GET`

**Authentication:** Required (Authenticated users only)

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `order_id` | UUID | Yes | The unique ID of the order |

### Example Requests

#### 1. **Get order details**
```bash
curl -X GET "http://localhost:8000/api/staff/orders/550e8400-e29b-41d4-a716-446655440000/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### Success Response (200 OK)

```json
{
  "success": true,
  "message": null,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "order_number": "ORD-5432",
    "status": "preparing",
    "payment_method": "hand_cash",
    "payment_status": "pending",
    "note": "Extra sauce on the side",
    "pickup_time": "20 minutes",
    "subtotal": "120.00",
    "service_fee": "10.00",
    "vat": "20.00",
    "total": "150.00",
    "branch_name": "Downtown Branch",
    "car": {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "car_model": "Toyota Camry",
      "plate_number": "ABC-1234",
      "car_color": "#CCCCCC"
    },
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440010",
        "menu_item_name": "Margarita Pizza",
        "menu_item_id": "550e8400-e29b-41d4-a716-446655440100",
        "quantity": 2,
        "unit_price": "45.00",
        "subtotal": "90.00"
      },
      {
        "id": "550e8400-e29b-41d4-a716-446655440011",
        "menu_item_name": "Caesar Salad",
        "menu_item_id": "550e8400-e29b-41d4-a716-446655440101",
        "quantity": 1,
        "unit_price": "30.00",
        "subtotal": "30.00"
      }
    ],
    "status_timestamps": {
      "accepted_at": "2026-04-18T10:35:00Z",
      "preparing_at": "2026-04-18T10:35:00Z",
      "ready_at": null,
      "delivered_at": null,
      "cancelled_at": null
    },
    "created_at": "2026-04-18T10:30:00Z"
  }
}
```

### Error Responses

#### 404 - Order Not Found
```json
{
  "success": false,
  "message": "Order not found.",
  "data": null
}
```

#### 403 - Unauthorized (Employee accessing another branch's order)
```json
{
  "success": false,
  "message": "Unauthorized.",
  "data": null
}
```

#### 401 - Not Authenticated
```json
{
  "success": false,
  "message": "Authentication credentials were not provided.",
  "data": null
}
```

---

## Order Status Values

| Status | Description |
|--------|-------------|
| `pending` | Order received, awaiting acceptance |
| `accepted` | Order accepted by staff |
| `preparing` | Order is being prepared |
| `ready` | Order is ready for pickup |
| `delivered` | Order has been delivered |
| `cancelled` | Order has been cancelled |

---

## Payment Methods

| Method | Description |
|--------|-------------|
| `stripe` | Online payment via Stripe |
| `hand_cash` | Cash payment on delivery |

---

## Payment Status Values

| Status | Description |
|--------|-------------|
| `pending` | Payment not yet received |
| `paid` | Payment received and confirmed |
| `failed` | Payment attempt failed |

---

## Authorization Logic

### How Access Control Works

```
For EMPLOYEE users:
  - Can only view orders where: order.branch == employee.branch
  - Authorization checked via: _can_manage_order(user, order)

For OWNER users:
  - Can view all orders where: order.branch.restaurant.owner == user

For ADMIN users:
  - Can view all orders in the system

If user role is none of the above:
  - Returns 403 Unauthorized
```

---

## Related Endpoints

### Order Management Actions

These endpoints allow employees to manage orders after viewing them:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/staff/orders/{order_id}/accept/` | POST | Accept order and start preparation |
| `/staff/orders/{order_id}/modify/` | POST | Send modification note to customer |
| `/staff/orders/{order_id}/ready/` | POST | Mark order as ready for pickup |
| `/staff/orders/{order_id}/cancel/` | POST | Cancel the order |
| `/staff/orders/{order_id}/confirm-cash/` | POST | Confirm cash payment received |
| `/staff/orders/scan-qr/` | POST | Scan QR code for delivery |

---

## Implementation Details

### Database Relationships

```
User (employee)
  └── employee_profile (OneToOne)
      └── branch (ForeignKey)
          └── orders (ForeignKey)
```

### Query Optimization

The list endpoint uses:
- **select_related**: Branch, Restaurant, Car, Customer (reduces N+1 queries)
- **prefetch_related**: Order items
- **ordering**: By created_at descending
- **pagination**: Default 20 items per page, max 100

### Code Location

- **Views**: [apps/checkout/views.py](apps/checkout/views.py#L673)
- **Serializers**: [apps/checkout/serializers.py](apps/checkout/serializers.py#L83)
- **Models**: [apps/checkout/models.py](apps/checkout/models.py)
- **URLs**: [apps/api/urls.py](apps/api/urls.py#L278)

---

## Common Issues & Troubleshooting

### Issue: Employee sees "Employee profile not found"
**Cause**: The authenticated user doesn't have an Employee profile
**Solution**: Ensure the user is created as an employee with an actual branch assigned

**Step to fix**:
```python
# In Django shell
from apps.authentication.models import User
from apps.restaurants.models import Employee, Branch

user = User.objects.get(username="employee_username")
branch = Branch.objects.get(id=branch_id)

# Create employee profile if missing
Employee.objects.create(user=user, branch=branch)
```

### Issue: Empty order list (status 200 but no data)
**Possible causes**:
1. No orders exist for the employee's branch
2. All orders have different status than filtered
3. Pagination page exceeds available pages

**Solution**: 
- Verify data exists: Check database for orders with matching branch
- Try without status filter: `/staff/orders/?page=1`
- Check metadata: The `pages` value tells total pages available

### Issue: Unauthorized (403) on valid order ID
**Cause**: Employee trying to access order from different branch
**Solution**: Employees can only access orders from their assigned branch. Verify order belongs to employee's branch.

---

## Testing

### Using Postman/cURL

1. **Get JWT Token**:
```bash
curl -X POST "http://localhost:8000/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"email":"employee@example.com","password":"password123"}'
```

2. **Use token in subsequent requests**:
```bash
curl -X GET "http://localhost:8000/api/staff/orders/?status=pending" \
  -H "Authorization: Bearer <token_from_step_1>"
```

3. **Test Pagination**:
```bash
curl -X GET "http://localhost:8000/api/staff/orders/?page=1&page_size=10" \
  -H "Authorization: Bearer <token_from_step_1>"
```

---

## Response Format

All responses follow a consistent format:

```json
{
  "success": true/false,
  "message": "Optional message",
  "data": {...},
  "meta": {...}  // Only in paginated responses
}
```

---

## Performance Considerations

- Default page size is 20 orders to prevent loading too many at once
- Maximum page size is 100 to prevent abuse
- Status filtering uses database indexes for fast queries
- Related data is optimized with select_related and prefetch_related

---

## Version
- **API Version**: 1.0
- **Last Updated**: April 18, 2026
- **Status**: Production
