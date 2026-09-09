/** @type {import('next').NextConfig} */
const nextConfig = {
  // Docker 多階段建置只複製 .next/standalone 產出，不需帶整個 node_modules（見 docker-compose.yml / frontend/Dockerfile）。
  output: "standalone",
};

export default nextConfig;
