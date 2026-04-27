import logging
import math
from decimal import Decimal
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import RestaurantCategory
from django.db import models

log = logging.getLogger(__name__)

# --- Utility Functions -----------------------------------------------------------------------


def calculate_distance(lat1, lon1, lat2, lon2):
    if not all([lat1, lon1, lat2, lon2]):
        return None
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)
 


# --- Exceptions --------------------------------------------------------------------------------


class RestaurantError(Exception):
    status_code = 400


class RestaurantNotFound(RestaurantError):
    status_code = 404


# Backward compatibility
MenuError = RestaurantError
MenuNotFoundError = RestaurantNotFound

# --- helper shared across services method ------------------------------------------------------------


def _get_restaurant_category(category_id) -> RestaurantCategory:
    try:
        return RestaurantCategory.objects.get(id=category_id)
    except RestaurantCategory.DoesNotExist:
        raise RestaurantNotFound(
            f"Restaurant category with id {category_id} does not exist."
        )


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
        queryset = RestaurantCategory.objects.annotate(
            restaurant_count=Count("restaurants")
        ).order_by("name")

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
                raise RestaurantError(
                    f"A category with name '{data.get('name')}' already exists."
                )
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
                raise RestaurantError(
                    f"A category with name '{data.get('name')}' already exists."
                )
            raise

        return category

    @staticmethod
    def delete_category(category_id: str) -> None:
        """Delete a category"""
        category = _get_restaurant_category(category_id)
        category.delete()
        log.info("Category deleted: id=%s", category_id)


# --- Branch SearchService -----------------------------------------------------------------------

class BranchSearchService:
    PAGE_SIZE = 10
 
    @staticmethod
    def search_branches(
        query: str = "",
        category_id: str = "",
        city: str = "",
        user_lat: float = None,
        user_lon: float = None,
        page: int = 1,
        radius_km: float = None,
    ) -> tuple:
        from apps.restaurants.models import Branch
        from apps.food_menus.models import MenuItem
 
        base_qs = (
            Branch.objects
            .filter(is_active=True, restaurant__is_active=True)
            .select_related("restaurant", "restaurant__category")
        )
 
        # Text search — branch name, restaurant name, or food item name
        if query:
            food_branch_ids = (
                MenuItem.objects
                .filter(name__icontains=query)
                .values_list("branch_id", flat=True)
                .distinct()
            )
            base_qs = base_qs.filter(
                Q(name__icontains=query) |
                Q(restaurant__brand_name__icontains=query) |
                Q(id__in=food_branch_ids)
            )
 
        # Filter by RESTAURANT category (not menu category)
        if category_id:
            base_qs = base_qs.filter(restaurant__category_id=category_id)
 
        if city:
            base_qs = base_qs.filter(city__icontains=city)
 
        branches = list(base_qs.order_by("-created_at"))
 
        # Distance annotation
        if user_lat is not None and user_lon is not None:
            for b in branches:
                if b.latitude and b.longitude:
                    b.distance = calculate_distance(
                        user_lat, user_lon,
                        float(b.latitude), float(b.longitude),
                    )
                else:
                    b.distance = None
 
            # Apply radius filter only if radius_km is set
            if radius_km is not None:
                branches = [
                    b for b in branches
                    if b.distance is not None and b.distance <= radius_km
                ]
 
            branches.sort(key=lambda x: (x.distance is None, x.distance or 0))
        else:
            for b in branches:
                b.distance = None
 
        paginator = Paginator(branches, BranchSearchService.PAGE_SIZE)
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
 