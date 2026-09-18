# Interfaz de CENTINELA — RI-08. Dos etapas: Node compila, nginx sirve.
# Lo que se despliega es nginx con los estáticos: sin Node ni node_modules.

# ---------------------------------------------------------------------------- build
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Sin variables VITE_*: el frontend usa rutas relativas y nginx las enruta. La misma imagen sirve
# para cualquier despliegue.
RUN npm run build

# ---------------------------------------------------------------------------- runtime
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
# Nombres de servicio de docker-compose.yml (misma red de compose).
ENV AGENTE2_UPSTREAM=agente-aprendizaje:8102 \
    AGENTE1_UPSTREAM=agente-identidad:8101
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -q -O - http://127.0.0.1/healthz || exit 1
