"""Registro de los modelos del dominio en el admin de Django."""

from django.contrib import admin

from farms.models import Animal, DailyYield, Farm, MilkRecord


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "municipality", "province"]
    list_filter = ["province"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"code": ["name"]}


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ["ear_tag", "farm", "breed", "birth_date", "lactation_number", "culled_date"]
    list_filter = ["breed", "farm"]
    search_fields = ["ear_tag"]
    list_select_related = ["farm"]
    autocomplete_fields = ["farm"]
    date_hierarchy = "birth_date"


@admin.register(DailyYield)
class DailyYieldAdmin(admin.ModelAdmin):
    list_display = ["animal", "date", "liters"]
    list_filter = ["animal__farm"]
    search_fields = ["animal__ear_tag"]
    list_select_related = ["animal"]
    autocomplete_fields = ["animal"]
    date_hierarchy = "date"


@admin.register(MilkRecord)
class MilkRecordAdmin(admin.ModelAdmin):
    list_display = ["animal", "date", "fat_pct", "protein_pct", "somatic_cell_count"]
    list_filter = ["animal__farm"]
    search_fields = ["animal__ear_tag"]
    list_select_related = ["animal"]
    autocomplete_fields = ["animal"]
    date_hierarchy = "date"
