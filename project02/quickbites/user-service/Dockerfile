FROM node:18-alpine

# Create a safe non-root user
RUN addgroup -S quickbite && adduser -S qbuser -G quickbite

WORKDIR /app

COPY package*.json ./
RUN npm install --only=production

COPY --chown=qbuser:quickbite . .

USER qbuser

EXPOSE 3001
# Change port for each service:
# user-service=3001, order-service=3002, restaurant-service=3003
# payment-service=3004, notification-service=3005

CMD ["node", "server.js"]

