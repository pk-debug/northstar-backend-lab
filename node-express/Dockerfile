# Educational image uses tsx at runtime for easier TypeScript learning.
FROM node:22-bookworm AS app
WORKDIR /app/node-express
COPY node-express/package.json ./
RUN npm install --no-audit --no-fund
COPY node-express/src ./src
COPY node-express/tsconfig.json ./
COPY shared/ /app/shared/
EXPOSE 3000
CMD ["npm","run","start"]
