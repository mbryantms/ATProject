/* Image-focus.js */
/* Original concept by Obormot, 15 February 2019 (GPL) */
/* Standalone rewrite for Atlas Tigers web application. */

(() => {
  'use strict';

  const DEBUG_LEVEL = 0;

  const ICONS = {
    'chevron-left-solid':
      '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M15.7 4.3a1 1 0 0 0-1.4 0L7.6 11l6.7 6.7a1 1 0 1 0 1.4-1.4L10.4 11l5.3-5.3a1 1 0 0 0 0-1.4z"></path></svg>',
    'chevron-right-solid':
      '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8.3 4.3a1 1 0 0 1 1.4 0L16.4 11l-6.7 6.7a1 1 0 1 1-1.4-1.4L13.6 11 8.3 5.7a1 1 0 0 1 0-1.4z"></path></svg>',
    'circle-notch-light':
      '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-dasharray="45 10"></circle></svg>',
    'copy-regular':
      '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 3a3 3 0 0 0-3 3v9h2V6a1 1 0 0 1 1-1h9V3z"></path><path fill="currentColor" d="M10 7a3 3 0 0 0-3 3v8a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-8a3 3 0 0 0-3-3zm0 2h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z"></path></svg>',
    'circle-check-solid':
      '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 2a10 10 0 1 0 10 10A10.011 10.011 0 0 0 12 2zm4.7 8.3-5.4 5.4a1 1 0 0 1-1.4 0l-2.3-2.3a1 1 0 0 1 1.4-1.4l1.6 1.59 4.7-4.69a1 1 0 0 1 1.4 1.4z"></path></svg>',
  };

  const notificationCenter = (() => {
    const listeners = new Map();

    return {
      addHandlerForEvent(eventName, handler) {
        if (!listeners.has(eventName)) listeners.set(eventName, new Set());
        listeners.get(eventName).add(handler);
      },
      removeHandlerForEvent(eventName, handler) {
        const set = listeners.get(eventName);
        if (!set) return;
        set.delete(handler);
        if (set.size === 0) listeners.delete(eventName);
      },
      fireEvent(eventName, payload = {}) {
        const set = listeners.get(eventName);
        if (!set) return;
        set.forEach((handler) => {
          try {
            handler(payload);
          } catch (error) {
            if (DEBUG_LEVEL >= 0) console.error(error);
          }
        });
      },
    };
  })();

  const GW = {
    isMobile: () => window.matchMedia('(max-width: 649px)').matches,
    mediaQueries: {
      portraitOrientation: '(orientation: portrait)',
    },
    svg: (iconName) => ICONS[iconName] || '',
    notificationCenter,
    defaultImageAuxText: '',
  };

  const mousemoveListeners = new Map();

  function GWLog(message, file, level = 1) {
    if (DEBUG_LEVEL < level) return;
    console.debug(`[${file}] ${message}`);
  }

  function addMousemoveListener(handler, { name }) {
    if (!name) throw new Error('addMousemoveListener requires a name.');
    removeMousemoveListener(name);
    const wrapped = (event) => handler(event);
    mousemoveListeners.set(name, wrapped);
    window.addEventListener('mousemove', wrapped);
  }

  function removeMousemoveListener(name) {
    const handler = mousemoveListeners.get(name);
    if (!handler) return;
    window.removeEventListener('mousemove', handler);
    mousemoveListeners.delete(name);
  }

  function togglePageScrolling(enable) {
    const root = document.documentElement;
    const body = document.body;
    if (!enable) {
      if (!root.dataset.imageFocusScrollLock) {
        root.dataset.imageFocusScrollLock = root.style.overflow || '';
        body.dataset.imageFocusScrollLock = body.style.overflow || '';
        root.style.overflow = 'hidden';
        body.style.overflow = 'hidden';
      }
    } else {
      if (root.dataset.imageFocusScrollLock !== undefined) {
        root.style.overflow = root.dataset.imageFocusScrollLock;
        delete root.dataset.imageFocusScrollLock;
      }
      if (body.dataset.imageFocusScrollLock !== undefined) {
        body.style.overflow = body.dataset.imageFocusScrollLock;
        delete body.dataset.imageFocusScrollLock;
      }
    }
  }

  function addUIElement(html) {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    const element = template.content.firstElementChild;
    document.body.appendChild(element);
    return element;
  }

  function doWhenMatchMedia(query, { ifMatchesOrAlwaysDo, callWhenAdd = false } = {}) {
    const mediaQuery = window.matchMedia(query);
    const handler = (event) => {
      ifMatchesOrAlwaysDo(event);
    };
    if (callWhenAdd) ifMatchesOrAlwaysDo(mediaQuery);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }

  function addActivateEvent(element, handler) {
    const onClick = (event) => handler(event);
    const onKeyDown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handler(event);
      }
    };
    element.addEventListener('click', onClick);
    element.addEventListener('keydown', onKeyDown);
    return () => {
      element.removeEventListener('click', onClick);
      element.removeEventListener('keydown', onKeyDown);
    };
  }

  if (!Element.prototype.addActivateEvent) {
    Object.defineProperty(Element.prototype, 'addActivateEvent', {
      value(handler) {
        return addActivateEvent(this, handler);
      },
    });
  }

  function onEventAfterDelayDo(
    element,
    eventName,
    delay,
    callback,
    { cancelOnEvents = [] } = {},
  ) {
    let timeoutId = null;
    const start = (event) => {
      timeoutId = window.setTimeout(() => callback(event), delay);
    };
    const cancel = () => {
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    };
    element.addEventListener(eventName, start, { passive: true });
    cancelOnEvents.forEach((cancelEvent) =>
      element.addEventListener(cancelEvent, cancel, { passive: true }),
    );
    return () => {
      element.removeEventListener(eventName, start);
      cancelOnEvents.forEach((cancelEvent) =>
        element.removeEventListener(cancelEvent, cancel),
      );
      cancel();
    };
  }

  function URLFromString(value) {
    try {
      return new URL(value, window.location.href);
    } catch {
      return new URL(window.location.href);
    }
  }

  function doAjax({ location }) {
    const img = new Image();
    img.src = location;
  }

  function newElement(tagName, attributes = {}, properties = {}) {
    const element = document.createElement(tagName);
    Object.entries(attributes || {}).forEach(([attr, value]) => {
      if (value != null) element.setAttribute(attr, value);
    });
    Object.assign(element, properties || {});
    return element;
  }

  function wrapElement(
    element,
    descriptor,
    { moveClasses = [], useExistingWrapper = false } = {},
  ) {
    const parts = descriptor.split('.');
    const tagName = parts.shift() || 'div';
    const classes = parts.filter(Boolean);
    let wrapper = element.parentElement;
    const matchesExisting =
      wrapper &&
      useExistingWrapper &&
      wrapper.tagName.toLowerCase() === tagName.toLowerCase() &&
      classes.every((cls) => wrapper.classList.contains(cls));
    if (!matchesExisting) {
      wrapper = document.createElement(tagName);
      if (classes.length) wrapper.classList.add(...classes);
      element.parentNode.insertBefore(wrapper, element);
      wrapper.appendChild(element);
    }
    moveClasses.forEach((cls) => {
      if (element.classList.contains(cls)) {
        element.classList.remove(cls);
        wrapper.classList.add(cls);
      }
    });
    return wrapper;
  }

  function revealElement(element) {
    if (!element || typeof element.scrollIntoView !== 'function') return;
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function relocate(target) {
    if (history.replaceState) {
      history.replaceState(null, '', target);
    } else {
      window.location.assign(target);
    }
  }

  function doWhenPageLoaded(callback) {
    if (document.readyState === 'complete') {
      callback();
    } else {
      window.addEventListener('load', callback, { once: true });
    }
  }

  function copyTextToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
    }
    return fallbackCopy(text);
  }

  function fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.top = '-1000px';
    textarea.setAttribute('readonly', '');
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand('copy');
    } finally {
      document.body.removeChild(textarea);
    }
    return Promise.resolve();
  }

  const ImageFocus = {
    contentImagesSelector: ['.markdownBody figure img'].join(', '),

    excludedContainerElementsSelector: ['a', 'button', 'figure.image-focus-not'].join(
      ', ',
    ),

    imageGalleryInclusionTest: (image) => {
      return (
        image.closest('#markdownBody') != null &&
        image.closest('.footnotes') == null &&
        image.classList.contains('page-thumbnail') == false
      );
    },

    shrinkRatio: 0.975,

    hideUITimerDuration: GW.isMobile() ? 5000 : 3000,

    dropShadowFilterForImages:
      'drop-shadow(10px 10px 10px #000) drop-shadow(0 0 10px #444)',

    hoverCaptionWidth: 175,
    hoverCaptionHeight: 75,

    fullSizeImageLoadHoverDelay: 25,

    imageFocusUIElementsSelector: [
      '.slideshow-button',
      '.help-overlay',
      '.image-number',
      '.caption',
      '.close-button',
    ].join(', '),

    focusableImagesSelector: null,
    focusedImageSelector: null,
    galleryImagesSelector: null,

    hideUITimer: null,

    overlay: null,

    mouseLastMovedAt: 0,

    currentlyFocusedImage: null,

    imageInFocus: null,

    savedHash: null,
    
    _dragStartMouseX: 0, // Added for drag event refactoring
    _dragStartMouseY: 0, // Added for drag event refactoring
    _dragStartImageX: 0, // Added for drag event refactoring
    _dragStartImageY: 0, // Added for drag event refactoring

    // Define the mousemove handler as a property of ImageFocus
    dragImageMouseMoveHandler: (moveEvent) => {
        ImageFocus.imageInFocus.style.filter = 'none';
        ImageFocus.imageInFocus.style.left =
            ImageFocus._dragStartImageX + moveEvent.clientX - ImageFocus._dragStartMouseX + 'px';
        ImageFocus.imageInFocus.style.top =
            ImageFocus._dragStartImageY + moveEvent.clientY - ImageFocus._dragStartMouseY + 'px';
    },

    setup: () => {
      GWLog('ImageFocus.setup', 'image-focus.js', 1);

      ImageFocus.overlay = addUIElement(`<div id="image-focus-overlay">
            <button type="button" class="close-button" tabindex="0" title="Close (Escape)">&times;</button>
            <div class="help-overlay">
                <p class="slideshow-help-text"><strong>Arrow keys:</strong> Next/previous image</p>
                <p><strong>Escape</strong> or <strong>click</strong>: Hide zoomed image</p>
                <p><strong>Space bar:</strong> Reset image size &amp; position</p>
                <p><strong>Scroll</strong> to zoom in/out</p>
                <p>(When zoomed in, <strong>drag</strong> to pan;<br><strong>double-click</strong> to reset size &amp; position)</p>
            </div>
            <div class="image-number"></div>
            <div class="slideshow-buttons">
                <button type="button" class="slideshow-button previous" tabindex="0" title="Previous image">
                    ${GW.svg('chevron-left-solid')}
                </button>
                <button type="button" class="slideshow-button next" tabindex="0" title="Next image">
                    ${GW.svg('chevron-right-solid')}
                </button>
            </div>
            <div class="caption"></div>
            <div class="loading-spinner">
                ${GW.svg('circle-notch-light')}
            </div>
        </div>`);

      doWhenMatchMedia(GW.mediaQueries.portraitOrientation, {
        ifMatchesOrAlwaysDo: () => {
          requestAnimationFrame(ImageFocus.resetFocusedImagePosition);
        },
        callWhenAdd: true,
      });

      ImageFocus.overlay.querySelectorAll('.slideshow-button').forEach((button) => {
        button.addActivateEvent((event) => {
          GWLog('ImageFocus.slideshowButtonClicked', 'image-focus.js', 2);
          ImageFocus.focusNextImage(event.target.classList.contains('next'));
          ImageFocus.cancelImageFocusHideUITimer();
          event.target.blur();
        });
      });

      // Close button handler
      const closeButton = ImageFocus.overlay.querySelector('.close-button');
      closeButton.addActivateEvent((event) => {
        GWLog('ImageFocus.closeButtonClicked', 'image-focus.js', 2);
        event.stopPropagation();
        ImageFocus.exitImageFocus();
      });

      // Click outside image to close (on overlay background)
      ImageFocus.overlay.addEventListener('click', (event) => {
        // Only close if clicking directly on the overlay background, not on UI elements
        if (event.target === ImageFocus.overlay) {
          GWLog('ImageFocus.overlayBackgroundClicked', 'image-focus.js', 2);
          ImageFocus.exitImageFocus();
        }
      });

      const helpOverlay = ImageFocus.overlay.querySelector('.help-overlay');
      if (GW.isMobile()) {
        helpOverlay.addEventListener('click', () => {
          helpOverlay.classList.toggle('open');
        });
      } else {
        helpOverlay.addEventListener('mouseenter', () => {
          helpOverlay.classList.add('open');
        });
        helpOverlay.addEventListener('mouseleave', () => {
          helpOverlay.classList.remove('open');
        });
      }

      ImageFocus.hideImageFocusUI();

      const suffixedSelector = (selector, suffix) =>
        selector
          .split(', ')
          .map((part) => part + suffix)
          .join(', ');

      ImageFocus.focusableImagesSelector = suffixedSelector(
        ImageFocus.contentImagesSelector,
        '.focusable',
      );
      ImageFocus.focusedImageSelector = suffixedSelector(
        ImageFocus.contentImagesSelector,
        '.focused',
      );
      ImageFocus.galleryImagesSelector = suffixedSelector(
        ImageFocus.contentImagesSelector,
        '.gallery-image',
      );

      ImageFocus.processImagesWithin(document);
      ImageFocus.updateGalleryMetadata();

      window.addEventListener('hashchange', ImageFocus.focusImageSpecifiedByURL);

      GW.notificationCenter.fireEvent('ImageFocus.setupDidComplete');
    },

    updateGalleryMetadata: () => {
      const galleryImages = document.querySelectorAll(ImageFocus.galleryImagesSelector);
      const numberIndicator = ImageFocus.overlay.querySelector('.image-number');
      numberIndicator.dataset.numberOfImages = galleryImages.length;
      if (galleryImages.length > 0) {
        galleryImages.forEach((image) => image.removeAttribute('accesskey'));
        galleryImages[0].accessKey = 'l';
      }
    },

    designateSmallImageIfNeeded: (image) => {
      const width = parseInt(image.getAttribute('width'), 10);
      const height = parseInt(image.getAttribute('height'), 10);
      if (
        Number.isFinite(width) &&
        Number.isFinite(height) &&
        (width < ImageFocus.hoverCaptionWidth || height < ImageFocus.hoverCaptionHeight)
      ) {
        image.classList.add('small-image');
      }
    },

    processImagesWithin: (container) => {
      GWLog('ImageFocus.processImagesWithin', 'image-focus.js', 1);

      container.querySelectorAll(ImageFocus.contentImagesSelector).forEach((image) => {
        if (image.closest(ImageFocus.excludedContainerElementsSelector)) return;

        image.classList.add('focusable');

        if (ImageFocus.imageGalleryInclusionTest(image))
          image.classList.add('gallery-image');

        ImageFocus.designateSmallImageIfNeeded(image);
      });

      container.querySelectorAll(ImageFocus.focusableImagesSelector).forEach((image) => {
        image.addEventListener('click', ImageFocus.imageClickedToFocus);
      });

      container.querySelectorAll(ImageFocus.focusableImagesSelector).forEach((image) => {
        image.removeAnnotationLoadEvents = onEventAfterDelayDo(
          image,
          'mouseenter',
          ImageFocus.fullSizeImageLoadHoverDelay,
          () => {
            ImageFocus.preloadImage(image);
            image.removeAnnotationLoadEvents();
          },
          { cancelOnEvents: ['mouseleave'] },
        );
      });

      container.querySelectorAll(ImageFocus.focusableImagesSelector).forEach((image) => {
        wrapElement(image, 'span.image-wrapper.focusable', {
          moveClasses: ['small-image'],
          useExistingWrapper: true,
        });
      });
    },

    focusedImgSrcForImage: (image) => {
      const imageSrcURL = URLFromString(image.src);
      if (
        imageSrcURL.hostname === 'upload.wikimedia.org' &&
        imageSrcURL.pathname.includes('/thumb/')
      ) {
        const parts = /(.+)thumb\/(.+)\/[^/]+$/.exec(imageSrcURL.pathname);
        if (parts) {
          imageSrcURL.pathname = parts[1] + parts[2];
        }
        return imageSrcURL.href;
      }
      if (image.srcset) {
        const matches = Array.from(image.srcset.matchAll(/(\S+?)\s+(\S+?)(,|$)/g));
        const lastMatch = matches[matches.length - 1];
        if (lastMatch) return lastMatch[1];
      }
      if (image.dataset.srcSizeFull) {
        return image.dataset.srcSizeFull;
      }
      return image.src;
    },

    expectedDimensionsForImage: (image) => {
      const width = parseInt(
        image.getAttribute('data-image-width') ??
          image.getAttribute('data-file-width') ??
          image.getAttribute('width'),
        10,
      );
      const height = parseInt(
        image.getAttribute('data-image-height') ??
          image.getAttribute('data-file-height') ??
          image.getAttribute('height'),
        10,
      );
      return Number.isFinite(width) && Number.isFinite(height)
        ? { width, height }
        : null;
    },

    preloadImage: (image) => {
      doAjax({ location: ImageFocus.focusedImgSrcForImage(image) });
    },

    focusImage: (imageToFocus, scrollToImage = true) => {
      GWLog('ImageFocus.focusImage', 'image-focus.js', 1);

      ImageFocus.enterImageFocus();
      ImageFocus.unhideImageFocusUI();
      ImageFocus.unfocusImage();

      imageToFocus.classList.toggle('focused', true);

      if (imageToFocus.classList.contains('gallery-image')) {
        const lastFocusedImage = document.querySelector('img.last-focused');
        if (lastFocusedImage) {
          lastFocusedImage.classList.remove('last-focused');
          lastFocusedImage.removeAttribute('accesskey');
        }

        const images = document.querySelectorAll(ImageFocus.galleryImagesSelector);
        const indexOfFocusedImage = ImageFocus.getIndexOfFocusedImage();
        ImageFocus.overlay.querySelector('.slideshow-button.previous').disabled =
          indexOfFocusedImage === 0;
        ImageFocus.overlay.querySelector('.slideshow-button.next').disabled =
          indexOfFocusedImage === images.length - 1;
        ImageFocus.overlay.querySelector('.image-number').textContent =
          indexOfFocusedImage + 1;

        if (!location.hash.startsWith('#if_slide_')) ImageFocus.savedHash = location.hash;
        relocate('#if_slide_' + (indexOfFocusedImage + 1));

        if (indexOfFocusedImage > 0)
          ImageFocus.preloadImage(images[indexOfFocusedImage - 1]);
        if (indexOfFocusedImage < images.length - 1)
          ImageFocus.preloadImage(images[indexOfFocusedImage + 1]);
      }

      ImageFocus.currentlyFocusedImage = imageToFocus;

      if (scrollToImage) revealElement(ImageFocus.currentlyFocusedImage);

      const src = ImageFocus.focusedImgSrcForImage(imageToFocus);
      const imageURL = URLFromString(src);
      if (imageURL.pathname.endsWith('.pdf')) {
        ImageFocus.imageInFocus = newElement('iframe', {
          src,
          class: 'image-in-focus',
          loading: 'eager',
        });
        ImageFocus.imageInFocus.setAttribute('frameborder', '0');
        ImageFocus.imageInFocus.style.backgroundColor = '#ffffff';
        ImageFocus.imageInFocus.style.border = 'none';
      } else {
        ImageFocus.imageInFocus = newElement(
          'img',
          {
            src,
            loading: 'eager',
            decoding: 'sync',
            style: `filter: ${imageToFocus.style.filter || 'none'} ${
              ImageFocus.dropShadowFilterForImages
            }`,
          },
          {},
        );

        if (imageToFocus.dataset.aspectRatio) {
          ImageFocus.imageInFocus.dataset.aspectRatio = imageToFocus.dataset.aspectRatio;
        }
      }
      ImageFocus.imageInFocus.classList.add('image-in-focus');

      ImageFocus.overlay.insertBefore(
        ImageFocus.imageInFocus,
        ImageFocus.overlay.querySelector('.loading-spinner'),
      );

      ImageFocus.resetFocusedImagePosition(true);

      ImageFocus.imageInFocus.addEventListener('mousedown', ImageFocus.imageMouseDown);
      ImageFocus.imageInFocus.addEventListener('dblclick', ImageFocus.doubleClick);

      ImageFocus.overlay.classList.toggle(
        'slideshow',
        imageToFocus.classList.contains('gallery-image'),
      );

      ImageFocus.setImageFocusCaption();

      GW.notificationCenter.fireEvent('ImageFocus.imageDidFocus', {
        image: imageToFocus,
      });
    },

    resetFocusedImagePosition: (updateOnLoad = false) => {
      GWLog('ImageFocus.resetFocusedImagePosition', 'image-focus.js', 2);

      if (ImageFocus.imageInFocus == null) return;

      const isImageElement = ImageFocus.imageInFocus.tagName === 'IMG';

      let imageWidth = 0;
      let imageHeight = 0;
      if (
        isImageElement &&
        URLFromString(ImageFocus.imageInFocus.src).pathname.endsWith('.svg')
      ) {
        if (ImageFocus.imageInFocus.dataset.aspectRatio) {
          ImageFocus.imageInFocus.style.aspectRatio =
            ImageFocus.imageInFocus.dataset.aspectRatio;
          const parts = ImageFocus.imageInFocus.dataset.aspectRatio.match(
            /([0-9]+)\s*\/\s*([0-9]+)/,
          );
          if (parts) {
            const aspectRatio = parseInt(parts[1], 10) / parseInt(parts[2], 10);
            imageWidth = window.innerHeight * aspectRatio;
            imageHeight = window.innerHeight;
          }
        } else {
          imageWidth = imageHeight = Math.min(window.innerWidth, window.innerHeight);
        }
      } else if (isImageElement) {
        if (updateOnLoad) {
          ImageFocus.imageInFocus.classList.add('loading');
          ImageFocus.imageInFocus.addEventListener(
            'load',
            () => {
              ImageFocus.imageInFocus.classList.remove('loading');
              ImageFocus.resetFocusedImagePosition();
            },
            { once: true },
          );
        }

        imageWidth = ImageFocus.imageInFocus.naturalWidth ?? 0;
        imageHeight = ImageFocus.imageInFocus.naturalHeight ?? 0;

        if (imageWidth * imageHeight === 0) {
          const expected = ImageFocus.expectedDimensionsForImage(
            ImageFocus.currentlyFocusedImage,
          );
          if (expected) {
            imageWidth = expected.width;
            imageHeight = expected.height;
          }
        }
      } else {
        imageWidth = Math.min(window.innerWidth * ImageFocus.shrinkRatio, window.innerWidth * 0.9);
        imageHeight = Math.min(
          window.innerHeight * ImageFocus.shrinkRatio,
          window.innerHeight * 0.9,
        );
      }

      if (imageWidth * imageHeight === 0) return;

      const constrainedWidth = Math.min(
        imageWidth,
        window.innerWidth * ImageFocus.shrinkRatio,
      );
      const widthShrinkRatio = constrainedWidth / imageWidth;
      const constrainedHeight = Math.min(
        imageHeight,
        window.innerHeight * ImageFocus.shrinkRatio,
      );
      const heightShrinkRatio = constrainedHeight / imageHeight;
      const shrinkRatio = Math.min(widthShrinkRatio, heightShrinkRatio);

      const width = Math.round(imageWidth * shrinkRatio);
      const height = Math.round(imageHeight * shrinkRatio);

      ImageFocus.imageInFocus.style.width = `${width}px`;
      ImageFocus.imageInFocus.style.height = `${height}px`;
      ImageFocus.imageInFocus.style.aspectRatio = isImageElement
        ? `${width} / ${height}`
        : '';
      ImageFocus.imageInFocus.style.left = '';
      ImageFocus.imageInFocus.style.top = '';

      ImageFocus.setFocusedImageCursor();
    },

    setFocusedImageCursor: () => {
      GWLog('ImageFocus.setFocusedImageCursor', 'image-focus.js', 2);

      if (ImageFocus.imageInFocus == null) return;

      ImageFocus.imageInFocus.style.cursor =
        ImageFocus.imageInFocus.height >= window.innerHeight ||
        ImageFocus.imageInFocus.width >= window.innerWidth
          ? 'move'
          : '';
    },

    unfocusImage: () => {
      GWLog('ImageFocus.unfocusImage', 'image-focus.js', 1);

      if (ImageFocus.imageInFocus) {
        ImageFocus.imageInFocus.remove();
        ImageFocus.imageInFocus = null;
      }

      if (ImageFocus.currentlyFocusedImage) {
        const unfocusedImage = ImageFocus.currentlyFocusedImage;
        ImageFocus.currentlyFocusedImage.classList.remove('focused');
        ImageFocus.currentlyFocusedImage = null;

        GW.notificationCenter.fireEvent('ImageFocus.imageDidUnfocus', {
          image: unfocusedImage,
        });
      }
    },

    enterImageFocus: () => {
      GWLog('ImageFocus.enterImageFocus', 'image-focus.js', 1);

      if (ImageFocus.overlay.classList.contains('engaged')) return;

      ImageFocus.overlay.classList.add('engaged');
      window.addEventListener('wheel', ImageFocus.scrollEvent, { passive: false });
      document.addEventListener('keyup', ImageFocus.keyUp);
      requestAnimationFrame(() => {
        togglePageScrolling(false);
      });

      if (GW.isMobile() === false)
        addMousemoveListener(ImageFocus.mouseMoved, { name: 'ImageFocusMousemoveListener' });

      window.addEventListener('mouseup', ImageFocus.mouseUp);

      GW.notificationCenter.fireEvent('ImageFocus.imageOverlayDidAppear');
    },

    exitImageFocus: () => {
      GWLog('ImageFocus.exitImageFocus', 'image-focus.js', 1);

      if (
        ImageFocus.currentlyFocusedImage &&
        ImageFocus.currentlyFocusedImage.classList.contains('gallery-image')
      ) {
        ImageFocus.currentlyFocusedImage.classList.remove('focused');
        ImageFocus.currentlyFocusedImage.classList.add('last-focused');
        ImageFocus.currentlyFocusedImage.accessKey = 'l';

        if (location.hash.startsWith('#if_slide_')) {
          const previousURL = URLFromString(location.href);
          previousURL.hash = ImageFocus.savedHash ?? '';
          relocate(previousURL.href);
          ImageFocus.savedHash = null;
        }
      }

      ImageFocus.unfocusImage();

      document.removeEventListener('keyup', ImageFocus.keyUp);
      window.removeEventListener('wheel', ImageFocus.scrollEvent);
      window.removeEventListener('mouseup', ImageFocus.mouseUp);
      if (GW.isMobile() === false)
        removeMousemoveListener('ImageFocusMousemoveListener');

      ImageFocus.overlay.classList.remove('engaged');

      requestAnimationFrame(() => {
        togglePageScrolling(true);
      });

      GW.notificationCenter.fireEvent('ImageFocus.imageOverlayDidDisappear');
    },

    getIndexOfFocusedImage: () => {
      const images = document.querySelectorAll(ImageFocus.galleryImagesSelector);
      let indexOfFocusedImage = -1;
      for (let i = 0; i < images.length; i += 1) {
        if (images[i].classList.contains('focused')) {
          indexOfFocusedImage = i;
          break;
        }
      }
      return indexOfFocusedImage;
    },

    focusNextImage: (forward = true) => {
      GWLog('ImageFocus.focusNextImage', 'image-focus.js', 1);

      const images = document.querySelectorAll(ImageFocus.galleryImagesSelector);
      if (images.length === 0) return;

      let indexOfFocusedImage = ImageFocus.getIndexOfFocusedImage();
      if (indexOfFocusedImage === -1) indexOfFocusedImage = 0;
      else indexOfFocusedImage += forward ? 1 : -1;
      indexOfFocusedImage = Math.max(0, Math.min(images.length - 1, indexOfFocusedImage));

      if (images[indexOfFocusedImage]) ImageFocus.focusImage(images[indexOfFocusedImage]);
    },

    setImageFocusCaption: () => {
      GWLog('ImageFocus.setImageFocusCaption', 'image-focus.js', 2);

      const captionContainer = ImageFocus.overlay.querySelector('.caption');
      captionContainer.replaceChildren();

      if (!ImageFocus.currentlyFocusedImage) return;

      const wrapper = document.createElement('div');
      wrapper.className = 'caption-text-wrapper';

      const figure = ImageFocus.currentlyFocusedImage.closest('figure');
      const figcaption = figure ? figure.querySelector('figcaption') : null;
      const title = ImageFocus.currentlyFocusedImage.getAttribute('title');

      const appendParagraph = (content, { allowHTML = false } = {}) => {
        if (!content) return;
        const paragraph = document.createElement('p');
        if (allowHTML) paragraph.innerHTML = content;
        else paragraph.textContent = content;
        wrapper.appendChild(paragraph);
      };

      if (figcaption) appendParagraph(figcaption.innerHTML, { allowHTML: true });
      appendParagraph(title);

      if (wrapper.children.length > 0) captionContainer.appendChild(wrapper);

      if (!ImageFocus.imageInFocus.src.startsWith('data:')) {
        const imageURLBlock = document.createElement('p');
        imageURLBlock.className = 'image-url';
        imageURLBlock.setAttribute('title', 'Click to copy image URL to clipboard');

        const urlCode = document.createElement('code');
        urlCode.className = 'url';
        urlCode.textContent = ImageFocus.truncatedURLString(
          ImageFocus.imageInFocus.src,
        );
        imageURLBlock.appendChild(urlCode);

        const iconContainer = document.createElement('span');
        iconContainer.className = 'icon-container';

        const normalIcon = document.createElement('span');
        normalIcon.className = 'icon normal';
        normalIcon.innerHTML = GW.svg('copy-regular');
        iconContainer.appendChild(normalIcon);

        const copiedIcon = document.createElement('span');
        copiedIcon.className = 'icon copied';
        copiedIcon.innerHTML = GW.svg('circle-check-solid');
        iconContainer.appendChild(copiedIcon);

        imageURLBlock.appendChild(iconContainer);
        captionContainer.appendChild(imageURLBlock);

        imageURLBlock.addActivateEvent((event) => {
          event.preventDefault();
          copyTextToClipboard(ImageFocus.currentlyFocusedImage.src).finally(() => {
            imageURLBlock.classList.add('copied', 'flash');
            setTimeout(() => {
              imageURLBlock.classList.remove('flash');
            }, 150);
          });
        });
        imageURLBlock.addEventListener('mouseleave', () => {
          imageURLBlock.classList.remove('copied');
        });
      }
    },

    truncatedURLString: (urlString) => {
      const maxLength = 160;
      return urlString.length > maxLength
        ? `${urlString.slice(0, maxLength)}…`
        : urlString;
    },

    focusImageSpecifiedByURL: () => {
      GWLog('ImageFocus.focusImageSpecifiedByURL', 'image-focus.js', 1);

      if (location.hash.startsWith('#if_slide_')) {
        doWhenPageLoaded(() => {
          const images = document.querySelectorAll(ImageFocus.galleryImagesSelector);
          const match = /#if_slide_([0-9]+)/.exec(location.hash);
          const imageIndex = match ? parseInt(match[1], 10) : NaN;
          if (Number.isFinite(imageIndex) && imageIndex > 0 && imageIndex <= images.length) {
            ImageFocus.focusImage(images[imageIndex - 1]);
          }
        });
      }
    },

    hideImageFocusUI: () => {
      GWLog('ImageFocus.hideImageFocusUI', 'image-focus.js', 3);

      ImageFocus.overlay
        .querySelectorAll(ImageFocus.imageFocusUIElementsSelector)
        .forEach((element) => element.classList.toggle('hidden', true));
    },

    hideUITimerExpired: () => {
      GWLog('ImageFocus.hideUITimerExpired', 'image-focus.js', 3);

      const timeSinceLastMouseMove = Date.now() - ImageFocus.mouseLastMovedAt;
      if (timeSinceLastMouseMove < ImageFocus.hideUITimerDuration) {
        ImageFocus.hideUITimer = setTimeout(
          ImageFocus.hideUITimerExpired,
          ImageFocus.hideUITimerDuration - timeSinceLastMouseMove,
        );
      } else {
        ImageFocus.hideImageFocusUI();
        ImageFocus.cancelImageFocusHideUITimer();
      }
    },

    unhideImageFocusUI: () => {
      GWLog('ImageFocus.unhideImageFocusUI', 'image-focus.js', 3);

      ImageFocus.overlay
        .querySelectorAll(ImageFocus.imageFocusUIElementsSelector)
        .forEach((element) => element.classList.toggle('hidden', false));

      ImageFocus.hideUITimer = setTimeout(
        ImageFocus.hideUITimerExpired,
        ImageFocus.hideUITimerDuration,
      );
    },

    cancelImageFocusHideUITimer: () => {
      GWLog('ImageFocus.cancelImageFocusHideUITimer', 'image-focus.js', 3);

      clearTimeout(ImageFocus.hideUITimer);
      ImageFocus.hideUITimer = null;
    },

    imageClickedToFocus: (event) => {
      GWLog('ImageFocus.imageClickedToFocus', 'image-focus.js', 2);
      ImageFocus.focusImage(event.currentTarget, false);
    },

    scrollEvent: (event) => {
      GWLog('ImageFocus.scrollEvent', 'image-focus.js', 3);

      event.preventDefault();

      const image = ImageFocus.imageInFocus;
      image.savedFilter = image.style.filter;
      image.style.filter = 'none';

      const imageBoundingBox = image.getBoundingClientRect();
      const factor =
        (image.height > 10 && image.width > 10) || event.deltaY < 0
          ? 1 + Math.sqrt(Math.abs(event.deltaY)) / 100
          : 1;

      image.style.width =
        (event.deltaY < 0 ? image.clientWidth * factor : image.clientWidth / factor) +
        'px';
      image.style.height = 'auto';

      const imageSizeExceedsWindowBounds =
        image.getBoundingClientRect().width > window.innerWidth ||
        image.getBoundingClientRect().height > window.innerHeight;
      const zoomingFromCursor =
        imageSizeExceedsWindowBounds &&
        imageBoundingBox.left <= event.clientX &&
        event.clientX <= imageBoundingBox.right &&
        imageBoundingBox.top <= event.clientY &&
        event.clientY <= imageBoundingBox.bottom;

      let zoomOrigin;
      if (zoomingFromCursor) {
        zoomOrigin = {
          clientX: event.clientX,
          clientY: event.clientY,
        };
      } else {
        zoomOrigin =
          event.deltaY > 0
            ? { clientX: window.innerWidth / 2, clientY: window.innerHeight / 2 }
            : {
                clientX: imageBoundingBox.left + imageBoundingBox.width / 2,
                clientY: imageBoundingBox.top + imageBoundingBox.height / 2,
              };
      }

      const originDeltaX = zoomOrigin.clientX - imageBoundingBox.left;
      const originDeltaY = zoomOrigin.clientY - imageBoundingBox.top;

      image.style.left =
        zoomOrigin.clientX - (originDeltaX * image.clientWidth) / imageBoundingBox.width + 'px';
      image.style.top =
        zoomOrigin.clientY -
        (originDeltaY * image.clientHeight) / imageBoundingBox.height +
        'px';

      requestAnimationFrame(() => ImageFocus.setFocusedImageCursor());
    },

    mouseUp: () => {
      GWLog('ImageFocus.mouseUp', 'image-focus.js', 2);

      if (ImageFocus.imageInFocus == null) return;

      const imageWasBeingDragged = ImageFocus._dragStartMouseX !== 0 || ImageFocus._dragStartMouseY !== 0;
      window.removeEventListener('mousemove', ImageFocus.dragImageMouseMoveHandler);

      // Reset drag start coordinates
      ImageFocus._dragStartMouseX = 0;
      ImageFocus._dragStartMouseY = 0;
      ImageFocus._dragStartImageX = 0;
      ImageFocus._dragStartImageY = 0;

      if (imageWasBeingDragged) {
        ImageFocus.imageInFocus.style.filter = ImageFocus.imageInFocus.savedFilter;
        ImageFocus.setFocusedImageCursor();
      }

      if (ImageFocus.hideUITimer == null) {
        ImageFocus.unhideImageFocusUI();
      }

      ImageFocus.overlay.querySelector('.caption').classList.remove('locked');

      if (
        ImageFocus.imageInFocus.height < window.innerHeight &&
        ImageFocus.imageInFocus.width < window.innerWidth
      ) {
        ImageFocus.imageInFocus.style.left = '';
        ImageFocus.imageInFocus.style.top = '';
      }
    },

    imageMouseDown: (event) => {
      GWLog('ImageFocus.imageMouseDown', 'image-focus.js', 2);

      if (event.button !== 0) return;
      event.preventDefault();

      if (
        ImageFocus.imageInFocus.height >= window.innerHeight ||
        ImageFocus.imageInFocus.width >= window.innerWidth
      ) {
        // Store initial positions to calculate drag offset
        ImageFocus._dragStartMouseX = event.clientX;
        ImageFocus._dragStartMouseY = event.clientY;

        const computedStyle = getComputedStyle(ImageFocus.imageInFocus);
        ImageFocus._dragStartImageX = parseInt(computedStyle.left, 10) || 0;
        ImageFocus._dragStartImageY = parseInt(computedStyle.top, 10) || 0;

        ImageFocus.imageInFocus.savedFilter = ImageFocus.imageInFocus.style.filter;

        // Attach event listener instead of direct assignment
        window.addEventListener('mousemove', ImageFocus.dragImageMouseMoveHandler);
      }
    },

    doubleClick: () => {
      GWLog('ImageFocus.doubleClick', 'image-focus.js', 2);

      if (
        ImageFocus.imageInFocus.height >= window.innerHeight ||
        ImageFocus.imageInFocus.width >= window.innerWidth
      )
        ImageFocus.resetFocusedImagePosition();
    },

    keyUp: (event) => {
      GWLog('ImageFocus.keyUp', 'image-focus.js', 3);

      const allowedKeys = [
        ' ',
        'Spacebar',
        'Escape',
        'Esc',
        'ArrowUp',
        'ArrowDown',
        'ArrowLeft',
        'ArrowRight',
        'Up',
        'Down',
        'Left',
        'Right',
      ];
      if (
        !allowedKeys.includes(event.key) ||
        getComputedStyle(ImageFocus.overlay).display === 'none'
      )
        return;

      event.preventDefault();

      switch (event.key) {
        case 'Escape':
        case 'Esc':
          ImageFocus.exitImageFocus();
          break;
        case ' ':
        case 'Spacebar':
          ImageFocus.resetFocusedImagePosition();
          break;
        case 'ArrowDown':
        case 'Down':
        case 'ArrowRight':
        case 'Right':
          if (
            ImageFocus.currentlyFocusedImage &&
            ImageFocus.currentlyFocusedImage.classList.contains('gallery-image')
          )
            ImageFocus.focusNextImage(true);
          break;
        case 'ArrowUp':
        case 'Up':
        case 'ArrowLeft':
        case 'Left':
          if (
            ImageFocus.currentlyFocusedImage &&
            ImageFocus.currentlyFocusedImage.classList.contains('gallery-image')
          )
            ImageFocus.focusNextImage(false);
          break;
        default:
          break;
      }
    },

    mouseMoved: (event) => {
      GWLog('ImageFocus.mouseMoved', 'image-focus.js', 3);

      const currentDateTime = Date.now();

      if (
        [ImageFocus.imageInFocus, ImageFocus.overlay, document.documentElement].includes(
          event.target,
        )
      ) {
        if (ImageFocus.hideUITimer == null) ImageFocus.unhideImageFocusUI();
        ImageFocus.mouseLastMovedAt = currentDateTime;
      } else {
        ImageFocus.cancelImageFocusHideUITimer();
      }
    },
  };

  window.ImageFocus = ImageFocus;

  document.addEventListener('DOMContentLoaded', () => {
    ImageFocus.setup();
    ImageFocus.focusImageSpecifiedByURL();
    GW.notificationCenter.fireEvent('ImageFocus.didLoad');
  });
})();
