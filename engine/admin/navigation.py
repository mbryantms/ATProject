"""Sidebar / index model ordering for the engine app.

Django lists an app's models alphabetically, which for ``engine`` interleaves
primary content (Post, Page) with taxonomy, media, and derived/diagnostic
tables (InternalLink, PostRevision, PostSimilarity, PostSlugHistory). This
orders them by likely operator workflow instead — content first, then taxonomy,
bibliography, media, configuration, and finally the system-maintained
diagnostic tables.

It wraps ``AdminSite.get_app_list`` idempotently (the same lightweight pattern
``celery_status.py`` uses for its URL) rather than adopting a custom
``AdminSite`` subclass, which would force every ``@admin.register`` call to be
rewritten. Unknown/newly-added models fall between configuration and
diagnostics and keep Django's alphabetical order, so nothing disappears.
"""

from django.contrib import admin

# Lower number sorts higher in the engine section.
_ENGINE_MODEL_ORDER = {
    # Content
    "Post": 10,
    "Page": 11,
    # Taxonomy
    "Series": 20,
    "Category": 21,
    "Tag": 22,
    "TagAlias": 23,
    # Bibliography
    "Source": 30,
    # Media
    "Asset": 40,
    "AssetFolder": 41,
    "AssetCollection": 42,
    "AssetTag": 43,
    # Configuration
    "SiteSettings": 50,
    # System-maintained / diagnostic (read-only)
    "InternalLink": 90,
    "PostRevision": 91,
    "PostSimilarity": 92,
    "PostSlugHistory": 93,
    "AssetMetadata": 94,
    "AssetRendition": 95,
}
# Unlisted engine models: between configuration and diagnostics.
_DEFAULT_ORDER = 60


def _sort_engine_models(app_list):
    for app in app_list:
        if app.get("app_label") == "engine":
            app["models"].sort(
                key=lambda m: (
                    _ENGINE_MODEL_ORDER.get(m.get("object_name"), _DEFAULT_ORDER),
                    m.get("name", ""),
                )
            )
    return app_list


def _install_app_list_once() -> None:
    if getattr(admin.site, "_engine_app_list_installed", False):
        return

    original_get_app_list = admin.site.get_app_list

    def patched_get_app_list(request, app_label=None):
        return _sort_engine_models(original_get_app_list(request, app_label))

    admin.site.get_app_list = patched_get_app_list
    admin.site._engine_app_list_installed = True


_install_app_list_once()
