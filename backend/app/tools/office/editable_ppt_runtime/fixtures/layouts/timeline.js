export const layoutName = "timeline";
export const render = ({ milestones = [] }) => `<section class="flex">${milestones.map(x => `<article>${x}</article>`).join("")}</section>`;
