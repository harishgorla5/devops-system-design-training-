FROM node:18-alpine
RUN addgroup -S quickbite && adduser -S qbuser -G quickbite
WORKDIR /app
COPY package*.json ./
RUN npm install --only=production
COPY --chown=qbuser:quickbite . .
USER qbuser
EXPOSE 3004
CMD ["node", "server.js"]

