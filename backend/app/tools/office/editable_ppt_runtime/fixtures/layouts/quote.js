export const layoutName = "quote";
export const render = ({ quote, source = "" }) => `<section><blockquote>${quote}</blockquote><cite>${source}</cite></section>`;
