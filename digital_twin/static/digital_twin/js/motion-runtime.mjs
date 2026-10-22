// Motion layer for the 3D viewer (trial): press feedback, sliding selection indicators, spring panel
// hide/show, value-change cues and a short staggered entrance.
// Library: Motion (vendor/motion/motion.js, MIT), loaded as a classic script that defines window.Motion.
// Rules followed (Motion AI Kit best practices): only transform/opacity, springs without overshoot for an
// operational UI, 150-400 ms, motion only for state change / relationship / feedback, and no motion at all
// when the user prefers reduced motion. Without Motion everything works as before (CSS states).

const M = globalThis.Motion;
// ?motion=1 forces the motion layer on for trying it out even when the OS asks for reduced motion
// (e.g. Windows "Animation effects" switched off); ?motion=0 forces it off.
const FORCED = typeof location === "object" ? new URLSearchParams(location.search).get("motion") : null;
const REDUCED = FORCED === "1" ? false : FORCED === "0" ? true
  : typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const PRESS = { type: "spring", bounce: 0, visualDuration: 0.12 };
const SETTLE = { type: "spring", bounce: 0, visualDuration: 0.25 };
const SLIDE = { type: "spring", bounce: 0, visualDuration: 0.3 };
const PANEL = { type: "spring", bounce: 0, visualDuration: 0.36 };

export function motionEnabled() {
  return Boolean(M && !REDUCED);
}

/** Short "this value changed" cue: rises into place while fading in. No-op without Motion. */
export function cueChange(element) {
  if (!motionEnabled() || !element) return;
  M.animate(element, { opacity: [0.25, 1], y: [4, 0] }, { duration: 0.24, ease: "easeOut" });
}

// Buttons whose own CSS transform (rotation, centring) must not be replaced by a scale.
const NO_PRESS = ".panel-collapse, .toolbar-toggle, .left-panels-toggle, .icon-button";

function pressFeedback(shell) {
  let pressed = null;
  const release = () => {
    if (pressed) M.animate(pressed, { scale: 1 }, SETTLE);
    pressed = null;
  };
  shell.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const control = event.target.closest?.("button, .display-control-group label");
    if (!control || control.matches(NO_PRESS) || control.disabled) return;
    pressed = control.matches("label") ? control.querySelector("b") ?? control : control;
    M.animate(pressed, { scale: 0.96 }, PRESS);
  });
  for (const type of ["pointerup", "pointercancel", "pointerleave"]) shell.addEventListener(type, release);
  shell.addEventListener("dragstart", release);
}

/** One highlight that slides to the pressed button of a group (instead of each button painting its own). */
function slidingIndicator(group, selector) {
  const indicator = document.createElement("span");
  indicator.className = "motion-indicator";
  indicator.setAttribute("aria-hidden", "true");
  group.prepend(indicator);
  group.classList.add("has-indicator");
  let placed = false;
  const place = (animated) => {
    const active = group.querySelector(`${selector}[aria-pressed="true"]`);
    if (!active) {
      M.animate(indicator, { opacity: 0 }, { duration: 0.15 });
      return;
    }
    const target = { x: active.offsetLeft, y: active.offsetTop, width: active.offsetWidth, height: active.offsetHeight, opacity: 1 };
    if (!animated || !placed) {
      Object.assign(indicator.style, { width: `${target.width}px`, height: `${target.height}px`, opacity: "1",
                                        transform: `translate(${target.x}px, ${target.y}px)` });
      placed = true;
      return;
    }
    M.animate(indicator, target, SLIDE);
  };
  new MutationObserver(() => place(true)).observe(group, { attributes: true, subtree: true, attributeFilter: ["aria-pressed"] });
  new ResizeObserver(() => place(false)).observe(group);
  place(false);
}

/** Spring hide/show for a set of panels driven by a data attribute on the shell ("hidden" / anything else). */
function panelToggle(shell, attribute, elements, offset) {
  let hidden = shell.dataset[attribute] === "hidden";
  const apply = () => {
    const nowHidden = shell.dataset[attribute] === "hidden";
    if (nowHidden === hidden) return;
    hidden = nowHidden;
    const items = elements().filter(Boolean);
    if (!hidden) for (const element of items) element.style.visibility = "visible";
    const animation = M.animate(items, hidden ? { ...offset(items), opacity: 0 } : { x: 0, y: 0, opacity: 1 },
                                { ...PANEL, delay: M.stagger(0.04, { from: hidden ? "last" : "first" }) });
    animation.then?.(() => {
      if (hidden && shell.dataset[attribute] === "hidden") for (const element of items) element.style.visibility = "hidden";
    });
  };
  new MutationObserver(apply).observe(shell, { attributes: true, attributeFilter: [`data-${attribute.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`] });
}

function entrance(shell) {
  const items = [".spatial-selector", ".ops-panel", ".display-controls", ".live-panel-position", ".viewer-toolbar"]
    .map((selector) => shell.querySelector(selector)).filter(Boolean);
  M.animate(items, { opacity: [0, 1], y: [8, 0] }, { duration: 0.35, ease: "easeOut", delay: M.stagger(0.05) });
}

export function initMotion(shell) {
  if (!motionEnabled() || !shell) return false;
  shell.classList.add("has-motion");
  pressFeedback(shell);
  const spans = shell.querySelector(".spatial-selector [role=group]");
  if (spans) slidingIndicator(spans, "[data-span-select]");
  const presets = shell.querySelector(".view-presets");
  if (presets) slidingIndicator(presets, "[data-view-preset]");
  panelToggle(shell, "leftPanels",
    () => [...shell.querySelectorAll(".spatial-selector, .ops-panel, .display-controls")],
    (items) => ({ x: -Math.max(...items.map((element) => element.offsetWidth)) - 24 }));
  panelToggle(shell, "toolbar",
    () => [shell.querySelector(".viewer-toolbar")],
    (items) => ({ y: items[0].offsetHeight + 24 }));
  entrance(shell);
  return true;
}
