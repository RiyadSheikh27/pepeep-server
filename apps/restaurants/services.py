""" 
All Restaurant related business logic here
Views only call services - no HTTP objects (Request/Response) in this file.
"""
import logging
import math
from decimal import Decimal
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import RestaurantCategory

log = logging.getLogger(__name__)

# --- Utility Functions -----------------------------------------------------------------------

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.
    Returns distance in kilometers.
    """
    if not all([lat1, lon1, lat2, lon2]):
        return None
    
    R = 6371  # Earth's radius in kilometers
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return round(distance, 2)

# --- Exceptions --------------------------------------------------------------------------------

class RestaurantError(Exception):
    status_code = 400

class RestaurantNotFound(RestaurantError):
    status_code = 404

# Backward compatibility
MenuError = RestaurantError
MenuNotFoundError = RestaurantNotFound

# --- helper shared across services method -----------------------------------------------------------------------

def _get_restaurant_category(category_id) -> RestaurantCategory:
    try:
        return RestaurantCategory.objects.get(id=category_id)
    except RestaurantCategory.DoesNotExist:
        raise RestaurantNotFound(f"Restaurant category with id {category_id} does not exist.")

    
# --- RestaurantCategoryService -----------------------------------------------------------------------

class RestaurantCategoryService:
    """CRUD operations for RestaurantCategory with pagination and search"""
    
    PAGE_SIZE = 10

    @staticmethod
    def list_categories(search: str = None, page: int = 1) -> tuple:
        """
        Get paginated list of categories with optional search.
        Returns: (items, total_count, page_number, total_pages, has_next, has_previous)
        """
        queryset = RestaurantCategory.objects.annotate(restaurant_count=Count('restaurants')).order_by('name')
        
        # Search by name
        if search:
            queryset = queryset.filter(Q(name__icontains=search))
        
        # Pagination
        paginator = Paginator(queryset, RestaurantCategoryService.PAGE_SIZE)
        try:
            page_obj = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)
        
        return (
            page_obj.object_list,
            paginator.count,
            page_obj.number,
            paginator.num_pages,
            page_obj.has_next(),
            page_obj.has_previous(),
        )
    
    @staticmethod
    def get_category_detail(category_id) -> RestaurantCategory:
        """Get category detail by id"""
        return _get_restaurant_category(category_id)
    
    @staticmethod
    def create_category(data: dict) -> RestaurantCategory:
        """Create a new category"""
        try:
            category = RestaurantCategory.objects.create(**data)
            log.info("Category created: id=%s name=%s", category.id, category.name)
            return category
        except Exception as e:
            if "unique" in str(e).lower():
                raise RestaurantError(f"A category with name '{data.get('name')}' already exists.")
            raise
    
    @staticmethod
    def update_category(category_id: str, data: dict) -> RestaurantCategory:
        """Update a category"""
        category = _get_restaurant_category(category_id)
        
        for field, value in data.items():
            setattr(category, field, value)
        
        try:
            category.save()
            log.info("Category updated: id=%s", category_id)
        except Exception as e:
            if "unique" in str(e).lower():
                raise RestaurantError(f"A category with name '{data.get('name')}' already exists.")
            raise
        
        return category
    
    @staticmethod
    def delete_category(category_id: str) -> None:
        """Delete a category"""
        category = _get_restaurant_category(category_id)
        category.delete()
        log.info("Category deleted: id=%s", category_id)


# --- RestaurantSearchService -----------------------------------------------------------------------

class RestaurantSearchService:
    PAGE_SIZE = 10

    @staticmethod
    def search_restaurants(
        query: str = "",
        category_id: str = "",
        city: str = "",
        user_lat: float = None,
        user_lon: float = None,
        page: int = 1,
    ) -> tuple:
        from .models import Restaurant
        from apps.food_menus.models import MenuItem

        base_qs = Restaurant.objects.filter(is_active=True).select_related("category")

        if query:
            by_name = base_qs.filter(
                Q(brand_name__icontains=query) | Q(legal_name__icontains=query)
            )
            food_restaurant_ids = (
                MenuItem.objects
                .filter(name__icontains=query)
                .values_list("branch__restaurant_id", flat=True)
                .distinct()
            )
            by_food = base_qs.filter(id__in=food_restaurant_ids)
            # Union — deduplicated by id
            combined_ids = set(by_name.values_list("id", flat=True)) | set(food_restaurant_ids)
            queryset = base_qs.filter(id__in=combined_ids)
        else:
            queryset = base_qs

        # Filter by category id (not name — see view change below)
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        if city:
            queryset = queryset.filter(city__icontains=city)

        restaurants = list(queryset.order_by("-created_at"))

        # Distance annotation + sort
        if user_lat is not None and user_lon is not None:
            for r in restaurants:
                if r.latitude and r.longitude:
                    r.distance = calculate_distance(
                        user_lat, user_lon,
                        float(r.latitude), float(r.longitude)
                    )
                else:
                    r.distance = None
            restaurants.sort(key=lambda x: (x.distance is None, x.distance or 0))
        else:
            for r in restaurants:
                r.distance = None

        paginator = Paginator(restaurants, RestaurantSearchService.PAGE_SIZE)
        try:
            page_obj = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)

        return (
            page_obj.object_list,
            paginator.count,
            page_obj.number,
            paginator.num_pages,
            page_obj.has_next(),
            page_obj.has_previous(),
        )