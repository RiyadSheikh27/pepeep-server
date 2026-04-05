# Menu - newly added
"""
Owner manages their own branch menus.
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.utils.custom_response import APIResponse
from apps.authentication.permissions import IsOwner
from apps.authentication.services import NotFound as AuthNotFound

from .models import MenuItem
from .serializers import (
    MenuCategoryListSerializer,
    MenuCategoryDetailSerializer,
    MenuCategoryWriteSerializer,
    MenuItemListSerializer,
    MenuItemDetailSerializer,
    MenuItemWriteSerializer,
    ModifierGroupSerializer,
    ModifierGroupWriteSerializer,
    ModifierOptionSerializer,
)
from .services import (
    MenuCategoryService,
    MenuItemService,
    ModifierGroupService,
    ModifierOptionService,
    MenuError,
    MenuNotFound,
    _get_branch,
)


# --- shared helper --------------------------------------------------------

def _menu_handle(exc):
    """ map a MenuError to an APIResponse error."""
    return APIResponse.error(
        errors={"detail": [str(exc)]},
        message=str(exc),
        status_code=getattr(exc, "status_code", 400),
    )


def _resolve_branch(request, branch_id):
    """
    Resolves the branch and returns (branch, None) on success
    or (None, error_response) on failure.
    """
    try:
        branch = _get_branch(request.user, branch_id)
        return branch, None
    except (MenuNotFound, AuthNotFound) as e:
        return None, _menu_handle(e)


# --- Category endpoints ---------------------------------------------------

class MenuCategoryListCreateView(APIView):
    """
    list of categories with item_count annotation (e.g. Burgers (7))
    create a new category
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request, branch_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        categories = MenuCategoryService.list_categories(branch)
        return APIResponse.success(
            data=MenuCategoryListSerializer(categories, many=True).data,
            meta={"count": categories.count()},
        )

    def post(self, request, branch_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        s = MenuCategoryWriteSerializer(
            data=request.data,
            context={"request": request, "branch": branch},
        )
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        category = MenuCategoryService.create_category(branch, s.validated_data)
        # Menu - newly added: re-fetch with annotation for consistent response shape
        category.item_count = 0
        return APIResponse.success(
            message="Category created.",
            data=MenuCategoryListSerializer(category).data,
            status_code=201,
        )


class MenuCategoryDetailView(APIView):
    """
    full category with items - groups - options (no N+1)
    update name / is_active / sort_order
    delete category and all its items
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request, branch_id, category_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            category = MenuCategoryService.get_category_detail(branch, category_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(data=MenuCategoryDetailSerializer(category).data)

    def patch(self, request, branch_id, category_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            # Menu - newly added: fetch existing instance so validate_name can exclude it
            existing = MenuCategoryService.get_category_detail(branch, category_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        s = MenuCategoryWriteSerializer(
            existing,
            data=request.data,
            partial=True,
            context={"request": request, "branch": branch},
        )
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            category = MenuCategoryService.update_category(branch, category_id, s.validated_data)
        except (MenuNotFound, MenuError) as e:
            return _menu_handle(e)
        category.item_count = existing.item_count
        return APIResponse.success(
            message="Category updated.",
            data=MenuCategoryListSerializer(category).data,
        )

    def delete(self, request, branch_id, category_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            MenuCategoryService.delete_category(branch, category_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(message="Category deleted.")


# --- Item endpoints ---------------------------------------------------

class MenuItemListCreateView(APIView):
    """
    flat list of all items in this branch (across all categories)
    create item (modifier groups added separately)
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request, branch_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        # Menu - newly added: select_related avoids N+1 on category name
        items = (
            MenuItem.objects
            .filter(branch=branch)
            .select_related("category")
            .order_by("category__sort_order", "sort_order", "name")
        )
        return APIResponse.success(
            data=MenuItemListSerializer(items, many=True).data,
            meta={"count": items.count()},
        )

    def post(self, request, branch_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        s = MenuItemWriteSerializer(
            data=request.data,
            context={"request": request, "branch": branch},
        )
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        # Menu - newly added: category is resolved by the serializer into validated_data["category"]
        category = s.validated_data.pop("category")
        item = MenuItemService.create_item(branch, category, {**s.validated_data, "category": category})
        return APIResponse.success(
            message="Item created. You can now add modifier groups (step 2).",
            data=MenuItemListSerializer(item).data,
            status_code=201,
        )


class MenuItemDetailView(APIView):
    """
    full item with modifier groups → options
    update any item field
    delete item and all modifier groups
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request, branch_id, item_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            item = MenuItemService.get_item_detail(branch, item_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(data=MenuItemDetailSerializer(item).data)

    def patch(self, request, branch_id, item_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            item = MenuItemService.get_item_detail(branch, item_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        s = MenuItemWriteSerializer(
            item,
            data=request.data,
            partial=True,
            context={"request": request, "branch": branch},
        )
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            updated = MenuItemService.update_item(branch, item_id, s.validated_data)
        except (MenuNotFound, MenuError) as e:
            return _menu_handle(e)
        return APIResponse.success(
            message="Item updated.",
            data=MenuItemListSerializer(updated).data,
        )

    def delete(self, request, branch_id, item_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            MenuItemService.delete_item(branch, item_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(message="Item deleted.")


class MenuItemToggleAvailabilityView(APIView):
    """
    /menu/branches/{branch_id}/items/{item_id}/toggle-availability/
    Flips is_available without needing a PATCH body.
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def post(self, request, branch_id, item_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            item = MenuItemService.toggle_availability(branch, item_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        status = "available" if item.is_available else "unavailable"
        return APIResponse.success(message=f"Item marked as {status}.", data={"is_available": item.is_available})


# --- Modifier Group endpoints -------------------------------------------------

class ModifierGroupListCreateView(APIView):
    """
    Menu - newly added
    GET  → all modifier groups for an item, with nested options (no N+1)
    POST → step 2: add a modifier group to an item
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request, branch_id, item_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            groups, item = ModifierGroupService.list_groups(branch, item_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(
            data=ModifierGroupSerializer(groups, many=True).data,
            meta={"item_name": item.name, "count": groups.count()},
        )

    def post(self, request, branch_id, item_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        s = ModifierGroupWriteSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            group = ModifierGroupService.create_group(branch, item_id, s.validated_data)
        except MenuNotFound as e:
            return _menu_handle(e)
        # Menu - newly added: attach annotation manually for serializer
        group.option_count = 0
        return APIResponse.success(
            message="Modifier group added.",
            data=ModifierGroupSerializer(group).data,
            status_code=201,
        )


class ModifierGroupDetailView(APIView):
    """
    update group name / type / min_select / max_select
    delete group and all its options
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def patch(self, request, branch_id, item_id, group_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        s = ModifierGroupWriteSerializer(data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            group = ModifierGroupService.update_group(branch, item_id, group_id, s.validated_data)
        except MenuNotFound as e:
            return _menu_handle(e)
        group.option_count = group.options.count()
        return APIResponse.success(
            message="Modifier group updated.",
            data=ModifierGroupSerializer(group).data,
        )

    def delete(self, request, branch_id, item_id, group_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            ModifierGroupService.delete_group(branch, item_id, group_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(message="Modifier group deleted.")


# --- Menu - newly added: Modifier Option endpoints -------------------------------------------------

class ModifierOptionCreateView(APIView):
    """
    Menu - newly added
    POST → add a new option to a modifier group
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def post(self, request, branch_id, item_id, group_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        s = ModifierOptionSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            option = ModifierOptionService.create_option(branch, item_id, group_id, s.validated_data)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(
            message="Option added.",
            data=ModifierOptionSerializer(option).data,
            status_code=201,
        )


class ModifierOptionDetailView(APIView):
    """
    update option name / price / option_type
    delete a single option
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def patch(self, request, branch_id, item_id, group_id, option_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        s = ModifierOptionSerializer(data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            option = ModifierOptionService.update_option(branch, item_id, group_id, option_id, s.validated_data)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(
            message="Option updated.",
            data=ModifierOptionSerializer(option).data,
        )

    def delete(self, request, branch_id, item_id, group_id, option_id):
        branch, err = _resolve_branch(request, branch_id)
        if err:
            return err
        try:
            ModifierOptionService.delete_option(branch, item_id, group_id, option_id)
        except MenuNotFound as e:
            return _menu_handle(e)
        return APIResponse.success(message="Option deleted.")