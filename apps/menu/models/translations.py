from django.db import models


class MenuTranslation(models.Model):
    menu = models.ForeignKey(
        "menu.Menu",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["menu_id", "language_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu", "language_code"],
                name="menu_translation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.language_code}] {self.name}"


class MenuCategoryTranslation(models.Model):
    category = models.ForeignKey(
        "menu.MenuCategory",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category_id", "language_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "language_code"],
                name="menu_category_translation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.language_code}] {self.name}"


class AllergenTranslation(models.Model):
    allergen = models.ForeignKey(
        "menu.Allergen",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["allergen_id", "language_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["allergen", "language_code"],
                name="allergen_translation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.language_code}] {self.name}"


class IngredientTranslation(models.Model):
    ingredient = models.ForeignKey(
        "menu.Ingredient",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ingredient_id", "language_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient", "language_code"],
                name="ingredient_translation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.language_code}] {self.name}"


class MenuItemTranslation(models.Model):
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["menu_item_id", "language_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_item", "language_code"],
                name="menu_item_translation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.language_code}] {self.name}"
