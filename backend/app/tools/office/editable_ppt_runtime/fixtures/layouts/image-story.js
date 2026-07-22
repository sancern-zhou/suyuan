export const layoutName = "image-story";
export const render = ({ image, caption = "" }) => `<section><img src="${image}"><p>${caption}</p></section>`;
