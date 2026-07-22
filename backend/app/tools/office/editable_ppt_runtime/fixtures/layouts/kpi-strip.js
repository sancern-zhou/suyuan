export const layoutName = "kpi-strip";
export const render = ({ values = [] }) => `<section class="flex">${values.map(x => `<strong>${x}</strong>`).join("")}</section>`;
