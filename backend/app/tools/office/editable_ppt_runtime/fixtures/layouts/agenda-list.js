export const layoutName = "agenda-list";
export const render = ({ title, items = [] }) => `<section><h1>${title}</h1><ol>${items.map(x => `<li>${x}</li>`).join("")}</ol></section>`;
