FROM node:22-alpine

WORKDIR /app

# Dependencies first: this layer is rebuilt only when package.json / the lockfile change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# The Vite dev server, same as running it by hand. --host makes it reachable from outside
# the container (by default it only listens on the container's own localhost).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
