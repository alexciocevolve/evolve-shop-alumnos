# Tienda didáctica

Una tienda en línea pequeña para aprender un stack completo: **React + FastAPI + SQLAlchemy + PostgreSQL**.
Se construye por *checkpoints*, en orden; cada uno termina con un commit y un tag de Git. El plan
completo (requisitos, decisiones y guion de clase) está en [`PLAN.md`](PLAN.md).

> El código, los comentarios, los mensajes de commit y los textos de pantalla están en inglés.
> El castellano queda solo para este README y para `PLAN.md`.

## Requisitos

- Docker (con Compose)
- Python 3.12 o superior
- Node.js 20 o superior

## Arranque

Copia la plantilla de variables de entorno (el `.env` real no se sube a Git):

```bash
cp .env.example .env
```

Base de datos (solo el servicio `db`; el esquema lo crea Alembic, no Docker):

```bash
docker compose up -d
```

Backend, en `http://localhost:8000` (documentación interactiva en `/docs`):

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt && alembic upgrade head && uvicorn app.main:app --reload
```

> En Linux o macOS el entorno virtual se activa con `source .venv/bin/activate`.

Frontend, en `http://localhost:5173`:

```bash
cd frontend && npm install && npm run dev
```

## Checkpoints

| Tag | Revisión Alembic | Qué se enseña | Estado |
|---|---|---|---|
| `cp1-catalog` | `001_products` | Una tabla bien hecha, un endpoint paginado, un listado que carga más al hacer scroll | hecho |
| `cp2-cart` | `002_cart_and_orders` | Carrito (mutable, efímero) frente a pedido (inmutable, precio congelado) | pendiente |
| `cp3-users` | `003_users_and_addresses` | Usuario, dirección de envío y de facturación, registro y login | pendiente |
| `cp4-price-history` | `004_price_history` | Un histórico que la base de datos rellena sola con un trigger en el `UPDATE` | pendiente |

Para ver el código de un checkpoint concreto: `git checkout cp1-catalog` (y `git checkout main` para volver).

## Moverse entre checkpoints con Alembic

Alembic guarda en la tabla `alembic_version` qué revisión está aplicada. Es el `schema_migrations`
de la sesión 15, hecho por la herramienta de verdad. Los comandos se ejecutan en `backend/` con el
entorno virtual activado:

```bash
alembic current
```

```bash
alembic upgrade head
```

```bash
alembic downgrade 001_products
```

```bash
alembic downgrade base
```

El `--rev-id` legible es deliberado: permite mover la **base de datos** entre checkpoints sin tocar
Git, y en clase se ve el esquema crecer y encoger. Así se crea cada revisión (el mismo comando en los
cuatro checkpoints, cambiando el id y el mensaje):

```bash
alembic revision --autogenerate --rev-id 001_products -m "products"
```

Para mirar la base de datos no hace falta instalar `psql`; se usa el del contenedor:

```bash
docker compose exec db psql -U shop -d shop
```

## Guion de demo

### cp1 · Catálogo

1. Abrir [`backend/app/models.py`](backend/app/models.py) y
   [`backend/alembic/versions/001_products.py`](backend/alembic/versions/001_products.py) lado a lado:
   qué generó Alembic (la tabla, los `CHECK`, el índice) y qué se añadió a mano (los 36 productos:
   autogenerate compara esquemas, no datos).
2. `\d products` en psql: el DDL coincide con lo que dicen los modelos.
3. `GET /products?limit=5` dos veces, la segunda con el `next_cursor` de la primera; la última página
   devuelve `"next_cursor": null`:

   ```bash
   curl "http://localhost:8000/products?limit=5"
   ```

   ```bash
   curl "http://localhost:8000/products?limit=5&cursor=5"
   ```

4. `GET /products/999` devuelve `404` con `{"detail": "Product 999 not found"}`.
5. Navegador con la pestaña **Red** abierta: bajar y ver las **tres** peticiones a `/products`
   (`cursor=0`, `cursor=12`, `cursor=24`) y las imágenes llegando después. Son dos mecanismos distintos:
   `loading="lazy"` retrasa **las imágenes**; el `IntersectionObserver` retrasa **la petición de la
   página siguiente**. Si la ventana es muy alta, el final de la lista ya está a la vista y se cargan las
   tres páginas de golpe: reduce la altura de la ventana o amplía el zoom del navegador.

## Fuera de alcance

Se dejan fuera a propósito (no se implementan):

- Pasarela de pago (un pedido nace ya en estado `paid`)
- Roles y permisos
- Docker para la aplicación (solo la base de datos va en Docker)
- CI
- Observabilidad
- Tests automáticos

## Observabilidad: los logs, en un Elasticsearch que no es nuestro

**Elasticsearch y Kibana no están en este `docker-compose.yml`, y es a propósito.** Viven
en el conjunto `elastic-real` de la sesión 24. Eso no es comodidad: el sitio donde se
guardan los logs es infraestructura compartida, con su propio ciclo de vida y su propia
factura. No se levanta y se tira con cada aplicación que quiera escribir en él, igual que
nadie mete su propio Postgres dentro del contenedor de su API.

Aquí solo queda lo que sí es de la tienda: quién recoge **sus** logs y a dónde los manda.

### Levantarlo

Primero el destino:

```bash
cd ../python-demo/sesion-24/elastic-real && docker compose up -d
```

Luego la credencial. La crea ese conjunto y hay que copiarla al `.env` de la tienda —
**decodificada**, ver `.env.example` para el porqué:

```bash
printf 'ELASTIC_API_KEY=%s
' "$(base64 -d < ../python-demo/sesion-24/elastic-real/secretos/clave-python)" >> .env
```

Y ya la tienda:

```bash
docker compose up -d --build
```

Kibana en **http://localhost:5601** (entra solo, sin login). El data stream se llama
**`logs-shop-evolve`**: crea una data view con ese patrón y `@timestamp` como campo de tiempo.

### La forma es la lección

**La tienda no sabe que Elasticsearch existe.** No hay cliente, ni host, ni credenciales,
ni librería: escribe líneas JSON por su salida estándar y ya. Filebeat las recoge. Si el
sistema de logs está caído, lento o se cambia por otro, la tienda sigue vendiendo — cosa
que no pasa con una aplicación que escribe directamente en Elasticsearch.

Y la única pieza que conoce los dos mundos es Filebeat, que por eso está conectado a **dos
redes de Docker**: la de la tienda y la de `elastic-real`. Un proyecto de compose no ve las
redes de los demás, y salir por el host tampoco vale porque `elastic-real` publica el 9200
solo en `127.0.0.1`.

### Por qué JSON, si se lee peor

`Order 12 failed for ana@example.com after 431ms` es agradable para una persona e inútil
para una máquina: responder *«¿cuál es el percentil 95 de latencia esta semana?»* significa
interpretar inglés con una expresión regular que se rompe en cuanto alguien reescriba el
mensaje. En campos, esa pregunta es un filtro y una agregación. El coste se paga una vez,
por quien programa, en lugar de cada vez que alguien le pregunta algo a los logs.

Los nombres son los de **ECS** (`http.response.status_code`, `url.path`,
`event.duration_ms`), el vocabulario de Elastic, para que Kibana sepa qué son sin configurar
nada.

### Dos streams, dos audiencias

| Stream | Qué lleva | Para qué |
|---|---|---|
| `logs-shop-evolve` | Lo que hace la tienda | Las preguntas del negocio |
| `logs-shop-filebeat` | Lo que hace el colector | Una sola pregunta, y hace falta |

Filebeat lee `/var/lib/docker/containers/*/*.log`, o sea **todo lo que corra en la
máquina**, y eso incluye su propia salida: se mete su informe de métricas cada 30 segundos
en el stream de la tienda. Es lo primero que aparece al abrir Kibana y hace pensar que la
integración no funciona.

La tentación es tirarlo, y estuvo tirado un rato. **Es un error.** Si Filebeat empieza a
fallar, sus logs son la única forma de enterarse: tirarlos es quedarse sin el aviso de que
has dejado de recibir avisos, que es la peor manera de estar ciego porque parece que todo
va bien.

Así que se aparta, no se tira. Se marca con `shop.log_source: collector` mientras las
etiquetas de Docker todavía existen, y el bloque `indices:` de la salida lo desvía. `indices`
se evalúa **antes** que `index`: la primera condición que encaja decide.

### El nombre del stream ES configuración

`logs-shop-evolve` no se llama así por gusto. Pasan dos cosas por elegirlo bien:

- La API key de `elastic-real` tiene alcance sobre `logs-*`. Un stream llamado
  `shop-evolve` a secas no se podría ni escribir ni leer.
- Elasticsearch **ya trae** una plantilla llamada `logs`, con patrón `logs-*-*` y data
  stream activado. `logs-` + `shop` + `-` + `evolve` encaja, así que el data stream, su
  ciclo de vida y su mapeo salen gratis.

Eso deja a la tienda con el permiso mínimo: escribir sus logs y nada más. Si Filebeat
tuviera que crear su propia plantilla necesitaría `manage_index_templates`, que es un
privilegio de clúster y no tiene por qué darse a una tienda.

### El hilo que une una petición

Cada petición recibe un `trace.id`, que también vuelve en la cabecera `X-Request-Id`.
Filtra por él en Kibana y tienes todo lo que pasó sirviendo un solo clic, en orden.
