import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom is not a browser: it has no layout, so it has no idea what is on screen and does
// not implement IntersectionObserver at all.
//
// The stand-in below reports "visible" as soon as something is observed, which is what a
// real browser does when the element is already in view - and it is what makes the
// catalog load its first page without anybody scrolling. The notification is sent
// asynchronously, like the real one, so React has finished rendering before it arrives.
// A test therefore sees the catalog behave as it does on a tall screen: it keeps asking
// for the next page until the server says there is not one.
//
// Written as a plain function, not a `class`, on purpose: `new` on a function that
// returns an object gives back that object, so this works, and the project's rule about
// having no classes in frontend/src holds in the tests too.
//
// It also honours disconnect(), like the real one: a notification that has not arrived
// yet is dropped once the observer is disconnected. StrictMode depends on that. It mounts
// every effect, cleans it up and mounts it again, and without this the first, already
// disconnected observer would still fire and the same page would be loaded twice.
vi.stubGlobal("IntersectionObserver", function fakeIntersectionObserver(
  callback: IntersectionObserverCallback,
) {
  let connected = true;
  return {
    observe: () =>
      queueMicrotask(() => {
        if (connected) callback([{ isIntersecting: true }] as never, null as never);
      }),
    unobserve: () => {},
    disconnect: () => {
      connected = false;
    },
    takeRecords: () => [],
    root: null,
    rootMargin: "",
    thresholds: [],
  };
});

// Same story with <dialog>. jsdom knows the element - HTMLDialogElement exists and `open`
// is there - but it does not implement showModal() or close(), so the product modal would
// throw the moment it opened. These stand-ins do the two things this code depends on:
// the element reports itself open, and close() fires the single `close` event that Escape,
// the × button and the click outside all end in.
//
// Note what they deliberately do NOT do: no backdrop, no focus trap, no Escape handling.
// Those are the browser's job and the reason the project used a native <dialog> in the
// first place, so a test here can never say they work. Only a real browser can.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});
