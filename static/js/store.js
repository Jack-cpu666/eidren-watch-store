"use strict";
const menuButton = document.querySelector(".menu-toggle");
const mobileNav = document.querySelector("#mobile-nav");
if (menuButton && mobileNav) {
  const closeMenu = () => { mobileNav.hidden = true; menuButton.setAttribute("aria-expanded", "false"); menuButton.setAttribute("aria-label", "Open navigation"); };
  menuButton.addEventListener("click", () => {
    const open = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    mobileNav.hidden = !open;
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !mobileNav.hidden) { closeMenu(); menuButton.focus(); } });
  window.matchMedia("(min-width: 901px)").addEventListener("change", event => { if (event.matches) closeMenu(); });
}
document.querySelectorAll("[data-quantity]").forEach(button => {
  button.addEventListener("click", () => {
    const input = button.parentElement.querySelector("input");
    const next = Number(input.value || 1) + Number(button.dataset.quantity);
    input.value = String(Math.max(Number(input.min || 1), Math.min(Number(input.max || 99), next)));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
});
document.querySelectorAll(".message-dismiss").forEach(button => button.addEventListener("click", () => button.parentElement.remove()));
document.querySelectorAll(".checkout-form, .add-to-bag-form").forEach(form => {
  form.addEventListener("submit", () => {
    if (!form.checkValidity()) return;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = form.classList.contains("checkout-form") ? "Opening secure checkout…" : "Adding to your bag…";
  });
});
window.addEventListener("pageshow", event => { if (event.persisted) window.location.reload(); });
if (new URLSearchParams(window.location.search).has("search")) document.querySelector("#watch-search")?.focus();

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
if (!reduceMotion.matches) {
  const revealTargets = [
    ".selected-section .section-heading",
    ".product-card",
    ".perspective-image",
    ".perspective-copy",
    ".closing-note > *",
    ".catalog-intro > *",
    ".catalog-controls",
    ".catalog-meta",
    ".editorial-heading",
    ".editorial-body",
    ".footer-top > *",
  ];
  document.querySelectorAll(revealTargets.join(",")).forEach((element) => {
    if (!element.hasAttribute("data-reveal")) element.setAttribute("data-reveal", element.matches(".perspective-image") ? "image" : "");
  });
  document.documentElement.classList.add("motion-ready");
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -10%", threshold: 0.08 });
  document.querySelectorAll("[data-reveal]").forEach((element) => revealObserver.observe(element));

  const heroImage = document.querySelector(".hero-image > img");
  const storyImage = document.querySelector(".perspective-image img");
  const tour = document.querySelector(".tour");
  const tourStage = document.querySelector(".tour-stage");
  const tourViewport = document.querySelector(".tour-viewport");
  const tourCards = [...document.querySelectorAll("[data-tour-card]")];
  const tourNumber = document.querySelector(".tour-number");
  const tourName = document.querySelector(".tour-name");
  const tourStatus = document.querySelector(".tour-status");
  if (tour && tourCards.length) tour.classList.add("tour-ready");
  let activeTourIndex = -1;

  const updateTour = () => {
    if (!tour || !tourCards.length) return;
    const rect = tour.getBoundingClientRect();
    const travel = Math.max(1, tour.offsetHeight - window.innerHeight);
    const progress = Math.max(0, Math.min(1, -rect.top / travel));
    const phase = progress * (tourCards.length - 1);
    const isMobile = window.innerWidth <= 640;
    const spread = isMobile ? 88 : 54;
    tourCards.forEach((card, index) => {
      const delta = index - phase;
      const distance = Math.abs(delta);
      const x = delta * spread;
      const z = distance * (isMobile ? -420 : -620);
      const y = Math.min(distance * 2.5, 6);
      const rotate = delta * (isMobile ? -13 : -24);
      card.style.transform = `translate3d(calc(-50% + ${x}vw), calc(-50% + ${y}vh), ${z}px) rotateY(${rotate}deg)`;
      card.style.opacity = String(Math.max(0.03, 1 - distance * 0.68));
      card.style.pointerEvents = distance < .52 ? "auto" : "none";
    });
    const nextIndex = Math.max(0, Math.min(tourCards.length - 1, Math.round(phase)));
    if (nextIndex !== activeTourIndex) {
      activeTourIndex = nextIndex;
      if (tourNumber) tourNumber.textContent = String(nextIndex + 1).padStart(2, "0");
      if (tourName) tourName.textContent = tourCards[nextIndex].dataset.tourName || "";
      tourCards.forEach((card, index) => {
        card.setAttribute("aria-hidden", index === nextIndex ? "false" : "true");
        card.querySelector("a")?.setAttribute("tabindex", index === nextIndex ? "0" : "-1");
      });
    }
    if (tourStatus) tourStatus.style.setProperty("--tour-progress", String((phase + 1) / tourCards.length));
  };
  let ticking = false;
  const updateMotion = () => {
    const scrollY = window.scrollY;
    if (heroImage) heroImage.style.setProperty("--parallax", `${Math.min(scrollY * 0.055, 34)}px`);
    if (storyImage) {
      const rect = storyImage.getBoundingClientRect();
      const centerOffset = rect.top + rect.height / 2 - window.innerHeight / 2;
      storyImage.style.setProperty("--parallax", `${Math.max(-24, Math.min(24, centerOffset * -0.035))}px`);
    }
    updateTour();
    ticking = false;
  };
  window.addEventListener("scroll", () => {
    if (!ticking) {
      window.requestAnimationFrame(updateMotion);
      ticking = true;
    }
  }, { passive: true });
  updateMotion();

  if (tourStage && tourViewport && window.matchMedia("(pointer:fine)").matches) {
    tourStage.addEventListener("pointermove", (event) => {
      const bounds = tourStage.getBoundingClientRect();
      const x = ((event.clientX - bounds.left) / bounds.width - .5) * 2;
      const y = ((event.clientY - bounds.top) / bounds.height - .5) * 2;
      tourViewport.style.setProperty("--look-x", `${x * 1.8}deg`);
      tourViewport.style.setProperty("--look-y", `${y * -1.2}deg`);
    });
    tourStage.addEventListener("pointerleave", () => {
      tourViewport.style.setProperty("--look-x", "0deg");
      tourViewport.style.setProperty("--look-y", "0deg");
    });
  }

  document.querySelectorAll(".product-image").forEach((card) => {
    card.addEventListener("pointermove", (event) => {
      const bounds = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${event.clientX - bounds.left}px`);
      card.style.setProperty("--my", `${event.clientY - bounds.top}px`);
    });
  });
}

const stickyHeader = document.querySelector(".site-header");
const scrollProgress = document.querySelector(".scroll-progress span");
let lastScrollY = window.scrollY;
window.addEventListener("scroll", () => {
  if (!stickyHeader) return;
  const currentScrollY = window.scrollY;
  const documentTravel = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
  if (scrollProgress) scrollProgress.style.transform = `scaleX(${Math.min(1, currentScrollY / documentTravel)})`;
  stickyHeader.classList.toggle("header-scrolled", currentScrollY > 20);
  stickyHeader.classList.toggle("header-hidden", currentScrollY > 180 && currentScrollY > lastScrollY + 3 && (!mobileNav || mobileNav.hidden));
  lastScrollY = currentScrollY;
}, { passive: true });
