declare module "*.svg" {
  const src: string;
  export default src;
}

declare module "*.png" {
  const src: string;
  export default src;
}

// Vite `?raw` import suffix — returns the asset's contents as a string.
// Used by `web/src/lib/helpArticles.ts` to inline the help corpus
// markdown at build time. Per gate-to-live plan Item 2.
declare module "*.md?raw" {
  const src: string;
  export default src;
}
