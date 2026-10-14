FROM node:22.22.3-bookworm-slim@sha256:e21fc383b50d5347dc7a9f1cae45b8f4e2f0d39f7ade28e4eef7d2934522b752 AS build
WORKDIR /srv/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.2-alpine@sha256:de3e40ec8b7debd7194fc798d4bbfb102c7f8b012b2c73032816b5f72393acdd AS runtime
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /srv/web/dist/career-web/browser /usr/share/nginx/html
USER 101
EXPOSE 8080
