FROM node:24.15-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --workspace @umbral/web --include-workspace-root

FROM node:24.15-alpine AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build --workspace @umbral/web

FROM node:24.15-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
RUN addgroup -S umbral && adduser -S -u 10001 -G umbral umbral
USER 10001
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
