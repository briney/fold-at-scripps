# fold@Scripps frontend build.
#
# The backend runs on the host (uv + systemd); only the SPA is built here so
# the host needs no Node. Extract the built assets with:
#   docker build --target dist --output type=local,dest=frontend/dist .
# which writes index.html + assets/ into ./frontend/dist for FastAPI to serve.
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Export-only stage: its filesystem is exactly the built dist.
FROM scratch AS dist
COPY --from=frontend-build /build/dist /
