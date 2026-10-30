# syntax=docker/dockerfile:1
# Multi-stage build
# Stage 1: Dependencies
FROM node:22-alpine AS deps
WORKDIR /app

# Install Python and build dependencies for native modules
# This helps with ARM64 builds and native module compilation
RUN apk add --no-cache python3 make g++ libc6-compat

# Copy package files
COPY ui/package*.json ./

# Clean install with proper handling of native modules
RUN --mount=type=cache,target=/root/.npm npm ci

# Stage 2: Builder
FROM node:22-alpine AS builder
WORKDIR /app

# Build a client installation without compiling owner-only admin pages into the
# distributable UI image. The API applies its own route gate separately.
ARG KODEWAVES_EDITION=saas
ARG KODEWAVES_RELEASE_PUBLIC_KEY=
ARG KODEWAVES_OWNER_STATUS_URL=

# Install libc6-compat for native modules in builder stage too
RUN apk add --no-cache libc6-compat

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy all files needed for build
COPY ui/package*.json ./
COPY ui/tsconfig.json ./
COPY ui/next.config.ts ./
COPY ui/components.json ./
COPY ui/sentry.edge.config.ts ./
COPY ui/sentry.server.config.ts ./
COPY ui/postcss.config.mjs ./
COPY ui/scripts/lucide-modularize-imports.ts ./scripts/lucide-modularize-imports.ts
COPY ui/public ./public
COPY ui/src ./src

RUN if [ "$KODEWAVES_EDITION" = "client" ]; then \
      rm -rf ./src/app/admin ./src/app/superadmin ./src/app/impersonate; \
    elif [ "$KODEWAVES_EDITION" != "saas" ]; then \
      echo "KODEWAVES_EDITION must be saas or client" >&2; exit 1; \
    fi

# Set build-time environment variables (needed for Next.js build)
ENV NEXT_PUBLIC_NODE_ENV="oss"
ENV NEXT_PUBLIC_KODEWAVES_EDITION=${KODEWAVES_EDITION}
ENV NEXT_TELEMETRY_DISABLED="1"
ENV BACKEND_URL="http://api:8000"
ENV KODEWAVES_EDITION=${KODEWAVES_EDITION}
RUN if [ "$KODEWAVES_EDITION" = "client" ]; then \
      test -n "$KODEWAVES_RELEASE_PUBLIC_KEY" && test -n "$KODEWAVES_OWNER_STATUS_URL" || \
        { echo "Client UI build requires the owner release key and status URL" >&2; exit 1; }; \
    fi && printf '%s' "$KODEWAVES_RELEASE_PUBLIC_KEY" > /app/client-release-public-key && \
       printf '%s' "$KODEWAVES_OWNER_STATUS_URL" > /app/client-owner-status-url

# Build the application with standalone mode
# Increase Node.js heap size to prevent out-of-memory errors during build
ENV NODE_OPTIONS="--max-old-space-size=4096"
# The marker lets deployment trim only this application's obsolete build snapshots.
RUN KODEWAVES_UI_BUILD=1 npm run build && \
    rm -rf /tmp/* /root/.npm /root/.next/cache /app/.next/cache

# Stage 3: Runner (production image)
FROM node:22-alpine AS runner
WORKDIR /app

# Environment variables will be provided by docker-compose
ARG KODEWAVES_EDITION=saas
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV KODEWAVES_EDITION=${KODEWAVES_EDITION}

# Create a non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/client-release-public-key ./client-release-public-key
COPY --from=builder --chown=nextjs:nodejs /app/client-owner-status-url ./client-owner-status-url
COPY --chown=nextjs:nodejs ui/scripts/verify-client-release.mjs ./verify-client-release.mjs

# Switch to non-root user
USER nextjs

# Expose the port Next.js runs on
EXPOSE 3010

# Start the production server using the standalone Node.js server
CMD sh -c "echo '🚀 Application ready at http://localhost:3010' && if [ \"$KODEWAVES_EDITION\" = client ]; then node ./verify-client-release.mjs --watch; else PORT=3010 node server.js; fi"
