// Pause autoplaying videos when the reader has requested reduced motion.
// CSS alone can't stop a <video> — it has to be done in script.

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const pauseAutoplayVideos = () => {
  document.querySelectorAll("video[autoplay]").forEach((video) => {
    video.removeAttribute("autoplay");
    try {
      video.pause();
    } catch (_) {
      // pause() can reject on some browsers if the player hasn't started
      // yet; we don't care — the removed attribute already did the work.
    }
  });
};

if (prefersReducedMotion()) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", pauseAutoplayVideos, {
      once: true,
    });
  } else {
    pauseAutoplayVideos();
  }
}
