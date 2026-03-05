# 阶段 1: 安装依赖
FROM node:20-alpine AS deps
WORKDIR /app

RUN npm config set registry https://registry.npmmirror.com
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# 阶段 2: 构建源码
FROM node:20-alpine AS builder
WORKDIR /app

RUN npm config set registry https://registry.npmmirror.com

# 硬编码 API URL
ENV NEXT_PUBLIC_API_URL=http://113.44.66.210:8000

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# 阶段 3: 生产运行环境
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=http://113.44.66.210:8000

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]

# 阶段 4: 开发环境
FROM node:20-alpine AS development
WORKDIR /app

RUN npm config set registry https://registry.npmmirror.com

ENV NEXT_PUBLIC_API_URL=http://113.44.66.210:8000
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["npm", "run", "dev"]
