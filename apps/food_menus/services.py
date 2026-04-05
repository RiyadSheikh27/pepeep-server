""" 
All Menu business logic Here
Views only call services - no HTTP objects (Request/Response) in this file.
"""

import logging
from django.db import transaction
from django.db.models import Count, Prefetch

from apps.restaurants.models import Branch
from .models import MenuCategory, MenuItem, ModifierGroup, ModifierOption

log = logging.getLogger(__name__)


# --- Exceptions ----------------------------------------------------------------------

class MenuError(Exception):
    status_code = 400

class MenuNotFound(MenuError):
    status_code = 404


# --- helpers shared across service methods -------------------------------------------

def _get_branch(owner, branch_id) -> Branch:
    """ resolve a branch that belongs to the authenticated owner. """
    try:
        return Branch.objects.get(id=branch_id, restaurant__owner=owner, is_active=True)
    except Branch.DoesNotExist:
        raise MenuNotFound("Branch not found or does not belong to you.")


def _get_category(branch, category_id) -> MenuCategory:
    """ resolve a category that belongs to the given branch."""
    try:
        return MenuCategory.objects.get(id=category_id, branch=branch)
    except MenuCategory.DoesNotExist:
        raise MenuNotFound("Category not found.")


def _get_item(branch, item_id) -> MenuItem:
    """ resolve an item that belongs to the given branch."""
    try:
        return MenuItem.objects.get(id=item_id, branch=branch)
    except MenuItem.DoesNotExist:
        raise MenuNotFound("Menu item not found.")


def _get_group(item, group_id) -> ModifierGroup:
    """ resolve a modifier group that belongs to the given item."""
    try:
        return ModifierGroup.objects.get(id=group_id, item=item)
    except ModifierGroup.DoesNotExist:
        raise MenuNotFound("Modifier group not found.")


def _get_option(group, option_id) -> ModifierOption:
    """ resolve an option that belongs to the given group."""
    try:
        return ModifierOption.objects.get(id=option_id, group=group)
    except ModifierOption.DoesNotExist:
        raise MenuNotFound("Modifier option not found.")


# --- MenuCategoryService ------------------------------------------------------

class MenuCategoryService:

    @staticmethod
    def list_categories(branch: Branch):
        """
        Returns all categories for a branch, annotated with item_count.
        """
        return (
            MenuCategory.objects
            .filter(branch=branch)
            .annotate(item_count=Count("items"))
            .order_by("sort_order", "name")
        )

    @staticmethod
    def get_category_detail(branch: Branch, category_id):
        """
        Full category with items - modifier groups - options.
        """
        try:
            return (
                MenuCategory.objects
                .filter(branch=branch)
                .annotate(item_count=Count("items"))
                .prefetch_related(
                    Prefetch(
                        "items",
                        queryset=MenuItem.objects
                            .filter(branch=branch)
                            .order_by("sort_order", "name")
                            .prefetch_related(
                                Prefetch(
                                    "modifier_groups",
                                    queryset=ModifierGroup.objects
                                        .order_by("sort_order", "name")
                                        .annotate(option_count=Count("options"))
                                        .prefetch_related(
                                            Prefetch(
                                                "options",
                                                queryset=ModifierOption.objects.order_by("sort_order", "name"),
                                            )
                                        ),
                                )
                            ),
                    )
                )
                .get(id=category_id)
            )
        except MenuCategory.DoesNotExist:
            raise MenuNotFound("Category not found.")

    @staticmethod
    @transaction.atomic
    def create_category(branch: Branch, data: dict) -> MenuCategory:
        """ create a new category for a branch."""
        return MenuCategory.objects.create(branch=branch, **data)

    @staticmethod
    @transaction.atomic
    def update_category(branch: Branch, category_id, data: dict) -> MenuCategory:
        """ partial update a category."""
        category = _get_category(branch, category_id)
        for field, value in data.items():
            setattr(category, field, value)
        category.save()
        return category

    @staticmethod
    @transaction.atomic
    def delete_category(branch: Branch, category_id):
        """
        Menu - newly added
        Delete a category. Cascades to all items and their modifier groups/options.
        """
        category = _get_category(branch, category_id)
        category.delete()
        log.info("Menu category deleted: id=%s branch=%s", category_id, branch.id)


# --- MenuItemService -------------------------------------------------------------

class MenuItemService:

    @staticmethod
    def get_item_detail(branch: Branch, item_id):
        """
        Menu - newly added
        Full item with modifier groups → options.
        All fetched in 3 queries (item + groups + options). No N+1.
        """
        try:
            return (
                MenuItem.objects
                .filter(branch=branch)
                .select_related("category")
                .prefetch_related(
                    Prefetch(
                        "modifier_groups",
                        queryset=ModifierGroup.objects
                            .order_by("sort_order", "name")
                            .annotate(option_count=Count("options"))
                            .prefetch_related(
                                Prefetch(
                                    "options",
                                    queryset=ModifierOption.objects.order_by("sort_order", "name"),
                                )
                            ),
                    )
                )
                .get(id=item_id)
            )
        except MenuItem.DoesNotExist:
            raise MenuNotFound("Menu item not found.")

    @staticmethod
    @transaction.atomic
    def create_item(branch: Branch, category: MenuCategory, data: dict) -> MenuItem:
        """
        create the item. Modifier groups are added separately.
        """
        return MenuItem.objects.create(branch=branch, **data)

    @staticmethod
    @transaction.atomic
    def update_item(branch: Branch, item_id, data: dict) -> MenuItem:
        """partial update an item (name, price, photo, etc.)."""
        item = _get_item(branch, item_id)
        for field, value in data.items():
            setattr(item, field, value)
        item.save()
        return item

    @staticmethod
    @transaction.atomic
    def delete_item(branch: Branch, item_id):
        """delete an item and all its modifier groups/options."""
        item = _get_item(branch, item_id)
        item.delete()
        log.info("Menu item deleted: id=%s branch=%s", item_id, branch.id)

    @staticmethod
    @transaction.atomic
    def toggle_availability(branch: Branch, item_id) -> MenuItem:
        """flip is_available on an item."""
        item = _get_item(branch, item_id)
        item.is_available = not item.is_available
        item.save(update_fields=["is_available", "updated_at"])
        return item


# --- ModifierGroupService -----------------------------------------------------------

class ModifierGroupService:

    @staticmethod
    def list_groups(branch: Branch, item_id):
        """
        All modifier groups for an item, with options nested.
        Fetched in 2 queries.
        """
        item = _get_item(branch, item_id)
        return (
            ModifierGroup.objects
            .filter(item=item)
            .order_by("sort_order", "name")
            .annotate(option_count=Count("options"))
            .prefetch_related(
                Prefetch(
                    "options",
                    queryset=ModifierOption.objects.order_by("sort_order", "name"),
                )
            )
        ), item

    @staticmethod
    @transaction.atomic
    def create_group(branch: Branch, item_id, data: dict) -> ModifierGroup:
        """add a modifier group to an item."""
        item = _get_item(branch, item_id)
        return ModifierGroup.objects.create(item=item, **data)

    @staticmethod
    @transaction.atomic
    def update_group(branch: Branch, item_id, group_id, data: dict) -> ModifierGroup:
        """partial update a modifier group."""
        item  = _get_item(branch, item_id)
        group = _get_group(item, group_id)
        for field, value in data.items():
            setattr(group, field, value)
        group.save()
        return group

    @staticmethod
    @transaction.atomic
    def delete_group(branch: Branch, item_id, group_id):
        """ delete a modifier group and all its options."""
        item  = _get_item(branch, item_id)
        group = _get_group(item, group_id)
        group.delete()
        log.info("Modifier group deleted: id=%s item=%s", group_id, item_id)


# --- ModifierOptionService ---------------------------------------------------------

class ModifierOptionService:

    @staticmethod
    @transaction.atomic
    def create_option(branch: Branch, item_id, group_id, data: dict) -> ModifierOption:
        """ add an option to a modifier group."""
        item   = _get_item(branch, item_id)
        group  = _get_group(item, group_id)
        return ModifierOption.objects.create(group=group, **data)

    @staticmethod
    @transaction.atomic
    def update_option(branch: Branch, item_id, group_id, option_id, data: dict) -> ModifierOption:
        """ partial update a modifier option."""
        item   = _get_item(branch, item_id)
        group  = _get_group(item, group_id)
        option = _get_option(group, option_id)
        for field, value in data.items():
            setattr(option, field, value)
        option.save()
        return option

    @staticmethod
    @transaction.atomic
    def delete_option(branch: Branch, item_id, group_id, option_id):
        """ delete a single modifier option."""
        item   = _get_item(branch, item_id)
        group  = _get_group(item, group_id)
        option = _get_option(group, option_id)
        option.delete()
        log.info("Modifier option deleted: id=%s group=%s", option_id, group_id)