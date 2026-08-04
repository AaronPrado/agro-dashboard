"""Registro de los modelos del dominio en el admin de Django."""

from django.contrib import admin

from farms.models import (
    AnalysisResult,
    Analyte,
    Animal,
    AnimalBatch,
    AnimalBatchMembership,
    BatchMilkSample,
    BatchRation,
    Crop,
    DailyYield,
    Farm,
    MilkRecord,
    NIRAnalysis,
    Plot,
    Ration,
    RationIngredient,
    RawMaterial,
    Silage,
    TargetProfile,
    TargetRange,
)


class RationIngredientInline(admin.TabularInline):
    model = RationIngredient
    extra = 1
    autocomplete_fields = ["silage", "raw_material"]


class NIRResultInline(admin.TabularInline):
    model = AnalysisResult
    fields = ["analyte", "value"]
    extra = 1
    autocomplete_fields = ["analyte"]
    verbose_name = "resultado"
    verbose_name_plural = "resultados"


class MilkResultInline(admin.TabularInline):
    model = AnalysisResult
    fields = ["analyte", "value"]
    extra = 1
    autocomplete_fields = ["analyte"]
    verbose_name = "resultado"
    verbose_name_plural = "resultados"


class TargetRangeInline(admin.TabularInline):
    model = TargetRange
    fields = ["analyte", "min_value", "max_value"]
    extra = 1
    autocomplete_fields = ["analyte"]


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


@admin.register(Plot)
class PlotAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "farm", "area_ha"]
    list_filter = ["farm"]
    search_fields = ["name", "code"]
    list_select_related = ["farm"]
    autocomplete_fields = ["farm"]


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ["plot", "species", "season", "sowing_date", "harvest_date"]
    list_filter = ["species", "season", "plot__farm"]
    search_fields = ["plot__name", "plot__code"]
    list_select_related = ["plot"]
    autocomplete_fields = ["plot"]


@admin.register(Silage)
class SilageAdmin(admin.ModelAdmin):
    list_display = ["code", "crop", "sealed_date", "opened_date"]
    list_filter = ["crop__species", "crop__plot__farm"]
    search_fields = ["code"]
    list_select_related = ["crop__plot"]
    autocomplete_fields = ["crop"]


@admin.register(NIRAnalysis)
class NIRAnalysisAdmin(admin.ModelAdmin):
    list_display = ["silage", "date", "laboratory"]
    list_filter = ["silage__crop__plot__farm"]
    search_fields = ["silage__code", "laboratory"]
    list_select_related = ["silage__crop"]
    autocomplete_fields = ["silage"]
    date_hierarchy = "date"
    inlines = [NIRResultInline]


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ["name", "category"]
    list_filter = ["category"]
    search_fields = ["name"]


@admin.register(AnimalBatch)
class AnimalBatchAdmin(admin.ModelAdmin):
    list_display = ["name", "farm"]
    list_filter = ["farm"]
    search_fields = ["name"]
    list_select_related = ["farm"]
    autocomplete_fields = ["farm"]


@admin.register(AnimalBatchMembership)
class AnimalBatchMembershipAdmin(admin.ModelAdmin):
    list_display = ["animal", "batch", "date_from", "date_to"]
    list_filter = ["batch__farm", "batch"]
    search_fields = ["animal__ear_tag", "batch__name"]
    list_select_related = ["animal", "batch"]
    autocomplete_fields = ["animal", "batch"]
    date_hierarchy = "date_from"


@admin.register(Ration)
class RationAdmin(admin.ModelAdmin):
    list_display = ["name", "farm", "formulated_on"]
    list_filter = ["farm"]
    search_fields = ["name"]
    list_select_related = ["farm"]
    autocomplete_fields = ["farm"]
    date_hierarchy = "formulated_on"
    inlines = [RationIngredientInline]


@admin.register(BatchRation)
class BatchRationAdmin(admin.ModelAdmin):
    list_display = ["batch", "ration", "date_from", "date_to"]
    list_filter = ["batch__farm"]
    search_fields = ["batch__name", "ration__name"]
    list_select_related = ["batch", "ration"]
    autocomplete_fields = ["batch", "ration"]
    date_hierarchy = "date_from"


@admin.register(Analyte)
class AnalyteAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "unit"]
    search_fields = ["name", "code"]


@admin.register(BatchMilkSample)
class BatchMilkSampleAdmin(admin.ModelAdmin):
    list_display = ["batch", "date", "laboratory"]
    list_filter = ["batch__farm"]
    search_fields = ["batch__name", "laboratory"]
    list_select_related = ["batch"]
    autocomplete_fields = ["batch"]
    date_hierarchy = "date"
    inlines = [MilkResultInline]


@admin.register(TargetProfile)
class TargetProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "code"]
    search_fields = ["name", "code"]
    inlines = [TargetRangeInline]
