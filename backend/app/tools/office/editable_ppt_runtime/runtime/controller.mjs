export function pageFromSearch(search, pageCount) {
  const raw = new URLSearchParams(search).get("page");
  if (raw === null || raw === "") return 1;
  if (!/^\d+$/.test(raw)) throw new Error("page must be an integer");
  const page = Number(raw);
  if (page < 1 || page > pageCount) {
    throw new Error(`page must be between 1 and ${pageCount}`);
  }
  return page;
}

export function stepPage(current, delta, pageCount) {
  return Math.min(pageCount, Math.max(1, current + delta));
}

export function bindKeyboardNavigation({ getPage, setPage, pageCount }) {
  const handler = (event) => {
    const forward = event.key === "ArrowRight" || event.key === " ";
    const backward = event.key === "ArrowLeft";
    if (!forward && !backward) return;
    event.preventDefault();
    setPage(stepPage(getPage(), forward ? 1 : -1, pageCount));
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}
