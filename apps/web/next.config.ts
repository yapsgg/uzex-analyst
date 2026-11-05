import type { NextConfig } from "next";

// eve is composed as a peer service in the root vercel.ts, so this stays a plain config.
// Cache Components + Partial Prefetching give instant navigations: pages render their static
// shell (header, layout) immediately and stream FastAPI data into <Suspense> fallbacks.
const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Vercel routes /eve/v1/* to the agent. Running the services by hand, EVE_DEV_URL does that job.
  async rewrites() {
    const eve = process.env.EVE_DEV_URL;
    return eve ? [{ source: "/eve/v1/:path*", destination: `${eve}/eve/v1/:path*` }] : [];
  },
};

export default nextConfig;
