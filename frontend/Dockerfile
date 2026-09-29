FROM node:24-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build && chown -R node:node /app
USER node
CMD ["npm", "start", "--", "--hostname", "0.0.0.0"]
