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
from .base import (
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    TimeStampedModel,
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

# Post models
from .post import (
    InternalLink,
    Post,
    PostManager,
    PostQuerySet,
)

# Page model
from .page import Page, PageFeaturedTag

# Asset models
from .asset import (
    Asset,
    AssetManager,
    AssetMetadata,
    AssetQuerySet,
    AssetRendition,
    PostAsset,
)

# Organization models
from .organization import (
    AssetCollection,
    AssetFolder,
    AssetTag,
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
    # Page
    "Page",
    "PageFeaturedTag",
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
]
