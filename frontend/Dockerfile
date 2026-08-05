FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

# Used by docker-compose (target: dev) for local development: `npm run dev`,
# `npm test`, `npm run lint`, `npm run typecheck`. Deliberately does NOT set
# NODE_ENV=production the way the `runner` stage below does — Next.js's dev
# server and Vitest each set the NODE_ENV they need at runtime on their own.
# Hardcoding "production" here previously meant every command run against
# this image inherited it, which for `npm test` specifically made React
# strip React.act (which @testing-library/react depends on) from every
# test run.
FROM node:22-slim AS dev
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

EXPOSE 3000
CMD ["npm", "start"]
