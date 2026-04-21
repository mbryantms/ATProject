"""
Models for the engine app.

This package contains all model definitions organized by domain:
- base: Base models and mixins (TimeStampedModel, SoftDeleteModel)
- taxonomy: Content taxonomy (Tag, TagAlias, Category, Series)
- post: Post content models (Post, InternalLink)
- asset: Asset management (Asset, AssetMetadata, AssetRendition, PostAsset)
- organization: Asset organization (AssetFolder, AssetTag, AssetCollection)
"""

# Base models and mixins
# Asset models
from .asset import (
    Asset,
    AssetManager,
    AssetMetadata,
    AssetQuerySet,
    AssetRendition,
    PostAsset,
)
from .base import (
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    TimeStampedModel,
)

# Citation (bibliography)
from .citation import PostCitation

# Organization models
from .organization import (
    AssetCollection,
    AssetFolder,
    AssetTag,
)

# Page model
from .page import Page, PageFeaturedCategory, PageFeaturedTag

# Post models
from .post import (
    InternalLink,
    Post,
    PostManager,
    PostQuerySet,
    PostRevision,
    PostSimilarity,
)

# Settings
from .settings import SiteSettings

# Source (bibliography)
from .source import (
    Source,
    SourceManager,
    SourceQuerySet,
    SourceType,
    UrlStatus,
)

# Taxonomy models
from .taxonomy import (
    Category,
    Series,
    Tag,
    TagAlias,
    TagManager,
    TagQuerySet,
)

__all__ = [
    # Base
    "TimeStampedModel",
    "SoftDeleteModel",
    "SoftDeleteQuerySet",
    "SoftDeleteManager",
    # Taxonomy
    "Tag",
    "TagAlias",
    "TagQuerySet",
    "TagManager",
    "Category",
    "Series",
    # Post
    "Post",
    "PostQuerySet",
    "PostManager",
    "InternalLink",
    "PostRevision",
    "PostSimilarity",
    # Page
    "Page",
    "PageFeaturedTag",
    "PageFeaturedCategory",
    # Asset
    "Asset",
    "AssetQuerySet",
    "AssetManager",
    "AssetMetadata",
    "AssetRendition",
    "PostAsset",
    # Organization
    "AssetFolder",
    "AssetTag",
    "AssetCollection",
    # Settings
    "SiteSettings",
    # Citation (bibliography)
    "PostCitation",
    # Source (bibliography)
    "Source",
    "SourceQuerySet",
    "SourceManager",
    "SourceType",
    "UrlStatus",
]
