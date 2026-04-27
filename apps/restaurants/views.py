from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from rest_framework.response import Response
from apps.utils.custom_response import APIResponse
from .services import (
    RestaurantCategoryService,
    BranchSearchService,
    RestaurantError,
    RestaurantNotFound,
)
from .serializers import (
    RestaurantCategoryListSerializer,
    RestaurantCategoryDetailSerializer,
    RestaurantCategoryWriteSerializer,
    BranchSearchSerializer,
    BookmarkSerializer,
)
from apps.restaurants.models import RestaurantBookmark, Branch

# --- Shared helper method -----------------------------------------------------------------------


def _handle_exception(exc):
    """Map an exception to an APIResponse error."""
    return APIResponse.error(
        errors={"detail": [str(exc)]},
        message=str(exc),
        status_code=getattr(exc, "status_code", 400),
    )


# --- Restaurant Category Views -----------------------------------------------------------------------


class RestaurantCategoryListCreateView(APIView):
    """
    GET  /api/v1/categories/ - List all categories with pagination and search
    POST /api/v1/categories/ - Create a new category (admin only)
    """

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        """List categories with pagination and search"""
        search = request.query_params.get("search", "")
        page = request.query_params.get("page", 1)

        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1

        items, total_count, page_number, total_pages, has_next, has_previous = (
            RestaurantCategoryService.list_categories(search=search, page=page)
        )

        return APIResponse.success(
            data=RestaurantCategoryListSerializer(items, many=True).data,
            meta={
                "total": total_count,
                "page": page_number,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_previous": has_previous,
            },
        )

    def post(self, request):
        """Create a new category (admin only)"""
        # This is typically admin-only, but we're using IsAuthenticatedOrReadOnly
        # You can add additional admin checks here if needed
        serializer = RestaurantCategoryWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error(errors=serializer.errors, message="Invalid input.")

        try:
            category = RestaurantCategoryService.create_category(
                serializer.validated_data
            )
            return APIResponse.success(
                message="Category created successfully.",
                data=RestaurantCategoryDetailSerializer(category).data,
                status_code=201,
            )
        except RestaurantError as e:
            return _handle_exception(e)


class RestaurantCategoryDetailView(APIView):
    """
    GET    /api/v1/categories/{id}/ - Get category details
    PATCH  /api/v1/categories/{id}/ - Update category
    DELETE /api/v1/categories/{id}/ - Delete category
    """

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, category_id):
        """Get category details"""
        try:
            category = RestaurantCategoryService.get_category_detail(category_id)
            return APIResponse.success(
                data=RestaurantCategoryDetailSerializer(category).data,
            )
        except RestaurantNotFound as e:
            return _handle_exception(e)

    def patch(self, request, category_id):
        """Update category (admin only)"""
        try:
            category = RestaurantCategoryService.get_category_detail(category_id)
        except RestaurantNotFound as e:
            return _handle_exception(e)

        serializer = RestaurantCategoryWriteSerializer(
            category,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return APIResponse.error(errors=serializer.errors, message="Invalid input.")

        try:
            updated_category = RestaurantCategoryService.update_category(
                category_id, serializer.validated_data
            )
            return APIResponse.success(
                message="Category updated successfully.",
                data=RestaurantCategoryDetailSerializer(updated_category).data,
            )
        except RestaurantError as e:
            return _handle_exception(e)

    def delete(self, request, category_id):
        """Delete category (admin only)"""
        try:
            RestaurantCategoryService.delete_category(category_id)
            return APIResponse.success(
                message="Category deleted successfully.",
            )
        except RestaurantNotFound as e:
            return _handle_exception(e)


# --- Restaurant Search View -----------------------------------------------------------------------


class RestaurantSearchView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        from apps.checkout.models import VisibilitySettings
        from apps.restaurants.serializers import BranchSearchSerializer

        query = request.query_params.get("q", "")
        category_id = request.query_params.get("category_id", "")
        city = request.query_params.get("city", "")

        try:
            page = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            page = 1

        try:
            user_lat = (
                float(request.query_params.get("user_lat"))
                if request.query_params.get("user_lat")
                else None
            )
            user_lon = (
                float(request.query_params.get("user_lon"))
                if request.query_params.get("user_lon")
                else None
            )
        except (ValueError, TypeError):
            user_lat = None
            user_lon = None

        # Apply global radius only when coordinates are provided
        radius_km = None
        if user_lat is not None and user_lon is not None:
            radius_km = float(VisibilitySettings.get().radius_km)

        items, total_count, page_number, total_pages, has_next, has_previous = (
            BranchSearchService.search_branches(
                query=query,
                category_id=category_id,
                city=city,
                user_lat=user_lat,
                user_lon=user_lon,
                page=page,
                radius_km=radius_km,
            )
        )

        return APIResponse.success(
            data=BranchSearchSerializer(items, many=True).data,
            meta={
                "total": total_count,
                "page": page_number,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_previous": has_previous,
                "radius_km": radius_km,
                "user_location": (
                    {"latitude": user_lat, "longitude": user_lon}
                    if user_lat is not None
                    else None
                ),
            },
        )

# --- Restaurant Bookmark Views -----------------------------------------------------------------------

class BookmarkView(APIView):
    """
    GET    /api/v1/user/bookmarks/              — list bookmarked restaurants
    POST   /api/v1/user/bookmarks/              — bookmark a restaurant
    DELETE /api/v1/user/bookmarks/{restaurant_id}/ — remove bookmark
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        bookmarks = RestaurantBookmark.objects.filter(customer=request.user).select_related(
            "branch", "branch__restaurant", "branch__restaurant__category"
        ).order_by("-created_at")
        return APIResponse.success(data=BookmarkSerializer(bookmarks, many=True).data, meta={"count": bookmarks.count()})
    
    def post(self, request):
        branch_id = request.data.get("branch_id")
        if not branch_id:
            return APIResponse.error(errors={"branch_id": ["This field is required."]})
        branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not branch:
            return APIResponse.error(message="Branch not found.", status_code=404)
        _, created = RestaurantBookmark.objects.get_or_create(customer=request.user, branch=branch)
        return APIResponse.success(message="Branch bookmarked." if created else "Already bookmarked.", status_code=201 if created else 200)
    
    def delete(self, request, restaurant_id):   # reuse param name — it's branch_id 
        deleted, _ = RestaurantBookmark.objects.filter(customer=request.user, branch_id=restaurant_id).delete()
        if not deleted:
            return APIResponse.error(message="Bookmark not found.", status_code=404)
        return APIResponse.success(message="Bookmark removed.")