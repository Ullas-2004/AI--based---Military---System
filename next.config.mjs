/** @type {import('next').NextConfig} */

// Where the Flask API lives. Defaults to localhost for `npm run dev`; docker
// compose sets this to the service name so the containers can find each other.
const API_ORIGIN = (process.env.API_ORIGIN || "https://ai-based-military-system-1.onrender.com").replace(/\/$/, "");

const nextConfig = {
  // Proxy /api/* to Flask so the browser stays on a single origin: no CORS
  // preflight, and the API host is never baked into the client bundle.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ];
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
