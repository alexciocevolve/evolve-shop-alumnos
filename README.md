# Tienda didáctica

Una tienda en línea pequeña para aprender un stack completo: **React + FastAPI + SQLAlchemy + PostgreSQL**.
Se construye por *checkpoints*, en orden; cada uno termina con un commit y un tag de Git.

> El código, los comentarios, los mensajes de commit y los textos de pantalla están en inglés.
> El castellano queda solo para este README y para `PLAN.md`.

## Requisitos

- Docker (con Compose)
- Python 3.12 o superior

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

## Las categorías, en su propia tabla (EXPAND-CONTRACT)

Al principio la categoría era una columna de texto en `products`: el nombre `'laptops'` repetido en ocho
filas. Ahora es una tabla `categories` y `products.category_id` que la referencia. Así el nombre se guarda
una sola vez, renombrar una categoría es un `UPDATE`, y una errata no puede inventarse una categoría nueva
porque la clave foránea la rechaza.

El cambio se hace en **dos migraciones**, no en una, y esa es la lección:

| Revisión | Qué hace | ¿Rompe el código que ya está funcionando? |
|---|---|---|
| `001c_categories_expand` | Crea `categories`, la llena con los nombres que ya había y añade `products.category_id` **anulable** | **No.** La columna de texto sigue ahí y sigue siendo la que lee la aplicación |
| `001d_categories_contract` | Pone `category_id` como obligatoria y **borra** la columna de texto | **Sí.** Todo lo que aún leyera `products.category` deja de funcionar |

Entre las dos hay una parada: el hueco donde se despliega el código nuevo y se comprueba que nadie usa ya
la columna vieja. Si algo va mal, el `downgrade` de CONTRACT vuelve atrás **con los datos**, porque el
nombre se puede reconstruir siguiendo la clave foránea. Hacerlo en una sola migración obligaría a parar la
tienda. Se puede ver el esquema encoger y volver a crecer:

```bash
docker compose exec backend alembic downgrade 001c_categories_expand
```

```bash
docker compose exec backend alembic upgrade head
```

Dos cosas que `--autogenerate` **no** sabe hacer aquí, y que están corregidas a mano en las revisiones:

- **Mover los datos.** Compara esquemas, no datos, así que creó la tabla vacía y la columna llena de
  `NULL`. El traspaso está escrito a mano, y lee los nombres de los propios productos (`SELECT DISTINCT`)
  en vez de llevar una lista escrita, para que no se pueda olvidar ninguno.
- **Deshacer CONTRACT.** Generó un `add_column` con `NOT NULL` y sin valor por defecto, que sobre una tabla
  con 36 filas PostgreSQL rechaza (*column "category" contains null values*). El `downgrade` correcto tiene
  tres pasos: añadir la columna anulable, rellenarla desde `categories`, y solo entonces exigir `NOT NULL`.

**La API no cambió.** `GET /products` sigue enviando `"category": "laptops"`, un nombre, que ahora se lee de
la fila relacionada. El contrato con el navegador es independiente del esquema. Lo que sí es nuevo es
`GET /categories`, que devuelve `[{"id": 1, "name": "laptops"}, …]`: antes el frontend llevaba la lista
escrita a mano y ahora la pide. Añade una fila a `categories` y aparecerá un botón más en la pantalla sin
tocar una línea de código.

```bash
curl -s "http://localhost:8000/categories"
```

## Checkpoints

| Tag | Revisión Alembic | Qué se enseña | Estado |
|---|---|---|---|
| `chkp1-catalog` | `001_products` | Una tabla bien hecha, un endpoint paginado, un listado que carga más al hacer scroll | hecho |
| `chkp2-frontend` | `001_products` | Una frontend básico para ver todos los productos del catálogo para cada categoria | hecho |
| `chkp3-custom-images` | `001b_product_images` | Se cambian las fotos a unas que no son de stock | hecho |
| `chkp4-separate-category` | `001c_categories_expand` y `001d_categories_contract` | Las categorías en su propia tabla, en dos migraciones (EXPAND-CONTRACT), y cada una con su log | hecho |
| `chkp5-modal-description` | `001d_categories_contract` | El detalle del producto en un `<dialog>` sin pedir nada al servidor, y el navegador avisando de que se ha abierto | hecho |
| `chkp6-cart` | `002_cart_and_orders` | Carrito (mutable, efímero) frente a pedido (inmutable, precio congelado), y un log por cada paso de la compra | hecho |
| `chkp7-user` | `003_users` | Registro, acceso y sesiones, y qué se puede escribir en un log cuando hay contraseñas y tokens por medio | hecho |
| `chkp8-address` | `003a_addresses` | Dirección de envío y de facturación, una de cada por persona, y en los logs solo el país | hecho |

Para ver el código de un checkpoint concreto: `git checkout chkp1-catalog` (y `git checkout main` para volver).

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
5. Pinchar en cualquier parte de una tarjeta: se abre el detalle con la imagen, la descripción, el
   precio y si queda stock. Se cierra pinchando fuera, con `Esc` o con la `×`. En la pestaña **Red**
   no aparece ningún `GET` nuevo: la descripción ya venía en el listado, así que el detalle no le pide
   datos al servidor. Lo único que sale es un `POST /products/{id}/views` que vuelve vacío (`204`).
   No trae nada: solo avisa al servidor de que alguien ha abierto ese producto, para que quede en
   los logs (ver [Qué cuenta la tienda](#qué-cuenta-la-tienda-además-de-http)).
6. Navegador con la pestaña **Red** abierta: bajar y ver las **tres** peticiones a `/products`
   (`cursor=0`, `cursor=12`, `cursor=24`) y las imágenes llegando después. Son dos mecanismos distintos:
   `loading="lazy"` retrasa **las imágenes**; el `IntersectionObserver` retrasa **la petición de la
   página siguiente**. Si la ventana es muy alta, el final de la lista ya está a la vista y se cargan las
   tres páginas de golpe: reduce la altura de la ventana o amplía el zoom del navegador.

### cp2 · Carrito y pedido

1. Abrir `cart_items` y `order_items` lado a lado en [`models.py`](backend/app/models.py). **Esa es la
   sesión**: `cart_items` **no** tiene columna de precio y `order_items` **sí**. Un carrito enseña el precio
   de hoy, leído de `products`; un pedido guarda el precio al que se compró.
2. El recorrido completo por curl. El token del carrito viaja en una cabecera, nunca en la dirección:

   ```bash
   curl -s -X POST http://localhost:8000/cart
   ```

   ```bash
   curl -s -X PUT http://localhost:8000/cart/items/1 -H "X-Cart-Token: TOKEN" -H "Content-Type: application/json" -d '{"quantity":2}'
   ```

   Repetir ese mismo `PUT` deja el carrito igual: **fija** la cantidad, no suma. Por eso reintentarlo tras
   un corte de red es inofensivo. `DELETE` quita la línea: cada verbo hace lo que dice su nombre.
3. La demostración del precio congelado. Hacer el pedido, cambiar el precio en psql y volver a leerlo:

   ```bash
   docker compose exec db psql -U shop -d shop -c "UPDATE products SET price_cents = 1 WHERE id = 1"
   ```

   ```bash
   curl -s http://localhost:8000/orders/1
   ```

   El pedido sigue diciendo 89900. El catálogo ya dice 1.
4. Pedir más unidades de las que hay: `409` con el detalle, y el stock **intacto**. Con dos líneas, una
   servible y otra no, no se mueve ninguna: el pedido es todo o nada.
5. La carrera de la sesión 14: dos carritos con la última unidad, pagando a la vez. Uno recibe `201` y el
   otro `409`, y el stock acaba en 0, nunca en −1. Lo consigue `SELECT ... FOR UPDATE` en `create_order`.
6. En el navegador: añadir desde el catálogo, `+` / `−` / `Remove` en el carrito, comprar y ver la
   confirmación. El carrito sobrevive a recargar la página, porque el token está en `localStorage`.
7. Lo mismo, visto desde Kibana. Filtrar por `shop.cart_ref` con el valor de cualquier línea `cart.*` da
   la historia de ese carrito en orden: creado, cada producto añadido o quitado y el pedido del final. El
   intento que falló en el paso 5 está en `event.action: order.create and event.outcome: failure`.

> **Todavía no hay usuarios.** Cada pedido se asigna al mismo cliente de prueba, definido en
> [`backend/app/config.py`](backend/app/config.py) como `PLACEHOLDER_CUSTOMER_EMAIL`. Por eso `POST /orders`
> no lleva cuerpo: los precios, el total y el comprador los decide el servidor. El registro, la
> autenticación y la asignación real del pedido llegan en el checkpoint siguiente.

### cp3 · Registro y acceso

1. Abrir [`models.py`](backend/app/models.py) y buscar dónde se guarda la contraseña. **No está.** Hay una
   columna `password_hash` y ningún sitio donde quepa una contraseña: eso no es un olvido, es el diseño.
2. Registrarse en la pantalla y mirar después la tabla en psql. Lo que hay es `scrypt$<sal>$<hash>`:

   ```bash
   docker compose exec db psql -U shop -d shop -c "SELECT email, left(password_hash, 30) FROM users"
   ```

   Registrar a dos personas **con la misma contraseña** y comparar: los hashes son distintos, porque cada
   uno lleva su propia sal. Por eso una tabla de hashes precalculados no sirve de nada.
3. Equivocarse de contraseña, y luego probar con un email que no existe. **El mensaje es el mismo**:
   *"Invalid email or password"*. Si dijera "ese email no está registrado", el formulario de acceso sería
   una forma de averiguar quién compra aquí. Y tardan lo mismo, porque el servidor hace el trabajo de
   comprobar el hash también cuando no hay usuario.
4. Ahora los mismos dos intentos en Kibana, con `event.action: user.login`. Aquí **sí** se distingue el
   motivo, en `event.reason`: `wrong_password` o `unknown_email`. El cliente no debe saberlo, pero quien
   vigila la tienda lo necesita: muchos `unknown_email` con direcciones distintas son alguien probando
   una lista de cuentas robadas en otra web; muchos `wrong_password` sobre el mismo `user.id` son alguien
   intentando adivinar la contraseña de una persona. Buscar la contraseña que se tecleó en los logs: no
   está, ni la buena ni la mala. El correo tampoco.
5. La contraseña en el navegador, con las herramientas de desarrollo abiertas:
   - `type="password"`, y el botón **Show** para verla cuando hace falta.
   - Si el campo estuviera controlado por React, la contraseña acabaría en el atributo `value` del HTML, y
     cualquier cosa que serialice el DOM se la llevaría en claro. Por eso el campo es **no controlado** y se
     lee del elemento al enviar. Se puede comprobar en la consola: `$0.getAttribute('value')` da `null`.
   - `autocomplete="username"` y `autocomplete="current-password"` / `"new-password"`: es lo que hace que un
     gestor de contraseñas guarde y rellene bien, y que el navegador no meta la contraseña vieja en el campo
     de la nueva.
   - Aviso de **Caps Lock**, que es la causa más común de que una contraseña correcta sea rechazada.
6. Cerrar sesión y mirar la tabla `sessions`: la fila **se ha borrado**. Olvidar el token solo en el
   navegador dejaría al token vivo 24 horas para quien lo hubiera copiado. En los logs, `user.login` y
   `user.logout` llevan el mismo `shop.session_ref`, así que se puede saber cuánto duró la visita.
7. Una sesión caducada: la fila sigue existiendo y aun así el token ya no vale, porque lo que manda es la
   fecha, no la existencia de la fila.

> **Todavía no hay direcciones ni pedidos asignados.** Este paso es solo la cuenta: registro, acceso y
> sesión. Los pedidos siguen yendo al cliente de prueba de cp2.

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

### Qué cuenta la tienda, además de HTTP

El middleware escribe una línea por petición (`GET /products 200`), que habla del servidor.
Las rutas escriben otra que habla del negocio, con sus campos bajo `shop.` porque ECS no
tiene vocabulario para un catálogo. En Kibana se filtra por `event.action`:

| `event.action` | Nivel | Cuándo | Campos |
|---|---|---|---|
| `catalogue.list` | info | `GET /products` | `shop.category`, `shop.products_returned`, `shop.product_ids`, `shop.cursor`, `shop.has_next_page` |
| `product.view` | info | `GET /products/{id}` y `POST /products/{id}/views` | `shop.view_source` (`api` o `modal`), `shop.product_id`, `shop.product_name`, `shop.category`, `shop.price_cents`, `shop.stock` |
| `product.miss` | warning | `GET /products/{id}` que no existe | `shop.product_id` |
| `categories.list` | info | `GET /categories` | `shop.categories_returned`, `shop.category_names` |
| `categories.empty` | warning | `GET /categories` sin ninguna categoría | — |
| `cart.create` | info | `POST /cart` | `shop.cart_ref` y el resumen del carrito |
| `cart.miss` | warning | Un token de carrito que no existe | `shop.cart_ref` |
| `cart.item.set` | info / warning | `PUT /cart/items/{id}`, bien (`success`) o sin stock (`failure`) | `shop.product_id`, `shop.quantity`, `error.message` si falla, y el resumen del carrito |
| `cart.item.remove` | info | `DELETE /cart/items/{id}` | `shop.product_id` y el resumen del carrito |
| `order.create` | info / warning | `POST /orders`, hecho (`success`) o rechazado (`failure`) | `shop.order_id`, `shop.order_total_cents`, `shop.order_lines`, `shop.order_units`, `shop.product_ids`, `shop.cart_ref`, `error.message` si falla |
| `order.miss` | warning | `GET /orders/{id}` que no existe | `shop.order_id` |
| `user.register` | info / warning | `POST /users`, hecho o con el correo ya registrado | `user.id` si sale bien, `event.reason: email_taken` si no |
| `user.login` | info / warning | `POST /login`, dentro o fuera | `user.id` y `shop.session_ref` si entra; `event.reason` (`wrong_password` o `unknown_email`) y `user.id` o `shop.email_ref` si no |
| `user.session` | info | Un token de sesión caducado o inventado (`401`) | `shop.session_ref` |
| `user.logout` | info | `POST /logout` | `shop.session_ref` |
| `user.address.save` | info | `PUT /me/addresses/{kind}` | `user.id`, `shop.address_kind` (`shipping` o `billing`), `shop.address_country` |
| `user.address.delete` | info | `DELETE /me/addresses/{kind}` | `user.id`, `shop.address_kind` |

El resumen del carrito son `shop.cart_ref`, `shop.cart_lines`, `shop.cart_units` y
`shop.cart_total_cents`. Van en cada línea para que cualquiera se entienda sola, sin tener que
buscar las anteriores.

Dos cosas de estas líneas que se repiten en el resto del curso:

- **`event.outcome`** es un campo de ECS que dice si la acción salió bien (`success`) o no
  (`failure`). Con él, una sola búsqueda (`event.outcome: failure`) enseña todo lo que la tienda ha
  rechazado, sea lo que sea.
- **El token del carrito no aparece nunca.** Quien tiene el token puede abrir el carrito, y los logs
  los lee más gente que la base de datos. En su lugar va `shop.cart_ref`, los primeros caracteres de
  su hash (`fingerprint()` en `observability.py`). El mismo token da siempre la misma huella, así que
  se puede seguir un carrito de principio a fin, pero con la huella no se puede abrir. El correo del
  cliente tampoco se escribe: es un dato personal y con el número de pedido basta.
- **Contraseñas y sesiones.** La contraseña no se escribe nunca, tampoco la que está mal: muchas
  veces es la buena de otra web, o la buena con una errata. El token de sesión va como huella
  (`shop.session_ref`), igual que el del carrito. Para decir quién es el usuario se usa `user.id`, que
  es el nombre que ECS ya tiene para eso: cuando ECS tiene un campo, se usa el suyo en vez de
  inventar uno bajo `shop.`.
- **Direcciones.** Nombre, calle, ciudad y código postal señalan una casa concreta, así que no se
  escriben. Del log sale solo el país (`shop.address_country`), que sirve para saber dónde viven los
  clientes y no dice quiénes son.

El servidor solo puede apuntar lo que le llega. Abrir el detalle de un producto no le pide nada
(los datos ya estaban en la página), así que, por sí solo, el backend nunca sabría que ha pasado.
Por eso el navegador hace un `POST /products/{id}/views` al abrirlo. Es lo mismo que hace cualquier
web con sus estadísticas: la página avisa de lo que ocurre en la pantalla, porque el servidor no
lo ve. Si ese aviso falla, el cliente no se entera y la tienda sigue funcionando.

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
