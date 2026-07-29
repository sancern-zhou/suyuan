export const layoutName = "card-grid";
export const render = ({ cards = [] }) => `<section class="grid grid-cols-3">${cards.map(x => `<article>${x}</article>`).join("")}</section>`;
