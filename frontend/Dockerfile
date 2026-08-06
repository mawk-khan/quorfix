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
# next.config.ts's rewrites() (the /api/* -> BACKEND_INTERNAL_URL proxy) is
# resolved once, here, at `next build` time in standalone-output mode — not
# re-read from the environment when the standalone server.js later starts.
# This is a genuine Next.js standalone-output constraint (confirmed by
# testing: a runtime-only `environment:` override in docker-compose.prod.yml
# was silently ignored, and every proxied request fell through to
# next.config.ts's http://localhost:8000 default instead), not an oversight
# — so this must be a build arg, not a runtime env var. Safe to bake in
# here: docker-compose.prod.yml's `backend` service is always reachable at
# this exact internal DNS name for this compose topology, it is not a
# secret, and it is passed as the same value via build.args so there is
# still one source of truth, not two.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL}
RUN npm run build

# Production runtime — built from Next.js's "standalone" output
# (next.config.ts sets output: "standalone"), a self-contained server.js
# plus only the node_modules Next actually traced as used at runtime,
# instead of copying the full node_modules tree. `public/` and
# `.next/static/` are not part of that trace and must be copied alongside
# it (Next's own documented pattern). node:22-slim already ships a non-root
# `node` user (uid/gid 1000) — no need to create one.
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

ARG VERSION=dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="git@bitbucket-claude:aivah/bug-fixer.git" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}"

COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000
ENV PORT=3000
# Docker always auto-populates HOSTNAME with the container ID, and Next's
# standalone server.js binds literally to whatever HOSTNAME holds instead
# of treating an unset value as "all interfaces" — without this override it
# silently binds only to the container's own IP, not 127.0.0.1, which is
# unreachable both from the healthcheck below and, less obviously, from
# some Docker network drivers' published-port paths.
ENV HOSTNAME=0.0.0.0

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
