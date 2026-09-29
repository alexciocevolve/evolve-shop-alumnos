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

## Tests

Los tests del backend se ejecutan contra una base de datos **aparte**, `shop_test`, que se crea sola la
primera vez y se construye **ejecutando las migraciones de verdad**. Nunca tocan la base de desarrollo,
así que no pueden llevarse por delante los datos de la clase.

```bash
cd backend && .venv/Scripts/activate && pip install -r requirements-dev.txt && pytest
```

Cada test corre dentro de una transacción que se deshace al terminar, así que todos empiezan con los
mismos 36 productos y sin usuarios. No hay que borrar nada a mano. Si tardan minutos en vez de segundos,
revisa que `DATABASE_URL` en `.env` diga `127.0.0.1` y no `localhost` (ver `.env.example`).

**Cómo saber si un test sirve para algo:** rompe a propósito la regla que vigila y comprueba que falla.

| Rompe esto | Debe fallar |
|---|---|
| Quitar `joinedload(Product.category)` en `services.py` | El test que cuenta consultas (el N+1) |
| Poner `price_cents=0` en el `OrderItem` en `services.py` | Los dos tests del precio congelado |
| Quitar `Order.user_id == user.id` del `WHERE` en `services.py` | El test de que un pedido solo lo lee su dueño |
| Hacer que `save_address` modifique la fila en `services.py` | Los tests del histórico de direcciones |
| Añadir el `email` al log de login fallido en `services.py` | Los tests de `test_logs.py` que buscan datos personales |
| Quitar `disable_existing_loggers=False` en `alembic/env.py` | Todos los tests de `test_logs.py`, porque la tienda se queda muda |
| Quitar `with_for_update()` de `create_order` | El test de concurrencia: *«both buyers got through»* |
| Devolver `403` en vez de `404` en un pedido ajeno | El test que comprueba que no se confirma su existencia |
| Añadir `password_hash` a la respuesta de un usuario | Los dos tests que revisan lo que sale por la API |
| Cambiar un modelo sin escribir la migración | El test de deriva, que es el único que dice **por qué** |
| Escribir `x_cart_token` en el log de `cart.miss` | El test de `test_api_logs.py` que busca el token del carrito |

Un test que no falla al romper lo que vigila no vigila nada.

**Los logs también se prueban.** [`tests/test_logs.py`](backend/tests/test_logs.py) llama a los servicios y
lee lo que han escrito, convertido en el mismo JSON que llega a Elasticsearch. Comprueba que un login
fallido dice por qué y de quién, y sobre todo lo que **no** puede aparecer: ni la contraseña (la buena ni
la mala), ni el token de sesión, ni el correo. Un log es una salida del programa como cualquier otra, y
lo que no se prueba acaba cambiando sin que nadie se entere.

Ese fichero encontró un fallo nada más escribirse. Los tests ejecutan las migraciones en el mismo proceso,
y el `env.py` de Alembic llamaba a `fileConfig(...)`, que por defecto **apaga todos los loggers que ya
existen**. A partir de ahí la tienda no escribía ni una línea, y ningún error lo avisaba. En producción no
se nota, porque la migración corre en otro proceso antes de arrancar el servidor. Lo arregla
`disable_existing_loggers=False`.

### Los tipos de test, y por qué son distintos

| Fichero | Cómo se aísla |
|---|---|
| `test_security.py` | No toca la base de datos: una función, un argumento, una respuesta |
| `test_*.py` (servicios), `test_api_*.py` y los dos de logs | Una transacción que se deshace al terminar |
| `test_concurrency.py` | **Confirma de verdad**, porque dos transacciones que no se ven no compiten por nada. Crea su propio producto en vez de tocar el stock de los 36 de siempre, y limpia con SQL a pelo para que un fallo no deje filas confirmadas detrás |
| `test_migrations.py` | **Su propia base de datos**, que crea y destruye, porque la vacía entera |

Los de la API van contra el `TestClient` de FastAPI, no contra un servidor levantado: prueban las rutas,
las dependencias, la validación y los códigos de estado, sin que nadie tenga que arrancar nada.

[`tests/test_api_logs.py`](backend/tests/test_api_logs.py) hace con las rutas lo mismo que
`test_logs.py` con los servicios, pero con los secretos llegando como llegan de verdad: en cabeceras y
en el cuerpo de la petición, que es justo por donde se cuelan en un log sin querer. Comprueba el token
del carrito, el de sesión, la contraseña, el correo y cada campo de una dirección.

Y también encontró un fallo. El `trace.id` se leía de la `ContextVar` **al formatear** la línea, no al
crearla. Por la consola funcionaba, porque allí se formatea en el acto, todavía dentro de la petición.
Pero cualquier cosa que formatee más tarde (los tests, o una cola que escribe en segundo plano) llegaba
cuando la petición ya había terminado y el id se perdía. Ahora el id se copia en la línea en el momento
de crearla (`_record_with_request_id` en `observability.py`).

Por último, `pytest.ini` convierte cualquier aviso en error. Eso destapó que `@app.on_event("startup")`
está deprecado en FastAPI: el mensaje `shop started` ahora sale de `lifespan`, que además escribe
`shop stopped` al parar. Dos `shop started` seguidos sin un `shop stopped` en medio significan que el
servidor no se paró: se cayó o lo mataron.

### Frontend

```bash
cd frontend && npm install && npm test
```

Con `vitest` y Testing Library, sobre `jsdom`. **Ninguno toca la red**: cada test dice lo que responde la
API, así que un fallo siempre habla de este código y nunca de que la tienda esté caída, lenta o con datos
de otra persona.

Son pocos y elegidos. Se prueba comportamiento, nunca la forma: no hay tests de `formatPrice` ni del
`Header`, porque no tienen forma de romperse en silencio.

| Rompe esto | Debe fallar |
|---|---|
| Hacer controlado el campo de contraseña | Los dos tests de que la contraseña no acaba en el HTML |
| `setItems(page.items)` en vez de concatenar | El test de que cada página se **añade** a las anteriores |
| Quitar la comprobación de `generation` | El test de la respuesta que llega tarde |
| Quitar `!user \|\| !shippingAddress` del botón | Los dos tests del botón de comprar bloqueado |
| Mandar `reportProductView` desde un `useEffect` del modal | El test de que abrir un producto avisa **una** vez |
| Quitar el `.catch(() => {})` de `reportProductView` | El test de que un aviso fallido no molesta al cliente |

El primero existe porque **ese fallo fue real**: con un `<input value={...}>` controlado, React escribe el
texto en el **atributo** `value`, y entonces cualquier cosa que serialice el DOM se lleva la contraseña en
claro.

Los dos últimos prueban la única pieza de observabilidad que vive en el navegador: el aviso de que se ha
abierto un producto ([`src/api.test.ts`](frontend/src/api.test.ts) y el último test de
[`Catalog.test.tsx`](frontend/src/pages/Catalog.test.tsx)). El de StrictMode importa porque StrictMode
ejecuta cada efecto dos veces mientras se desarrolla: si el aviso saliera de un efecto, cada visita
contaría doble en Kibana.

> `jsdom` no tiene maquetación, así que no sabe qué se ve y no trae `IntersectionObserver`. El doble está
> en [`src/setupTests.ts`](frontend/src/setupTests.ts) y avisa de «visible» en cuanto se observa algo, que
> es lo que hace un navegador de verdad cuando el elemento ya está a la vista. Por eso, en los tests, el
> catálogo se comporta como en una pantalla alta: sigue pidiendo páginas hasta que el servidor dice que no
> hay más. El doble también respeta `disconnect()`, como el de verdad; sin eso, el test con StrictMode
> cargaba la misma página dos veces y enseñaba cada producto repetido.

### De extremo a extremo

Con la tienda levantada, desde `e2e/`:

```bash
docker compose up -d
```

```bash
cd e2e && ../backend/.venv/Scripts/python -m pytest
```

Si la tienda no está arrancada, se saltan con un mensaje que lo dice, en vez de fallar quince veces.

Son **17 y hablan solo HTTP y SQL**: no hay navegador. La regla que los define está en
[`e2e/conftest.py`](e2e/conftest.py) y conviene leerla antes que los tests:

> **Ninguno importa la aplicación.** Ni un solo `from app import ...`.

Un test que importa el código que prueba puede pasar mientras los contenedores están mal conectados, las
migraciones no se han ejecutado, el CORS apunta a otro sitio o las imágenes no se están sirviendo. Eso es
justo lo que esta capa existe para cazar.

**Prueba de que sirven:** con `CORS_ORIGINS` apuntando a una dirección equivocada, los 166 tests de backend
y frontend pasan igual y **dos de estos fallan**. Con el contenedor del frontend parado, falla el que
comprueba que se está sirviendo. La tienda estaría rota en cualquier navegador y nada más se habría enterado.

**Escriben en la base de datos de verdad**, porque es la que usa la tienda en marcha. Por eso traen **su
propio producto y su propio cliente** y se los llevan al terminar: los 36 productos de siempre no se tocan y
el stock no queda cambiado.

#### Los logs, hasta Elasticsearch

[`e2e/test_logs_in_elastic.py`](e2e/test_logs_in_elastic.py) sigue a los logs hasta donde alguien los va a
leer. Los tests de `backend/` comprueban lo que dice una línea; estos comprueban que **llega**: que sale del
contenedor, que Filebeat la recoge y que Elasticsearch la guarda con sus campos. Esa parte del viaje no la
ve nadie desde dentro de la tienda.

- El primero manda una petición con una cabecera `X-Request-Id` inventada (el middleware respeta la que
  trae el cliente) y la busca en `logs-shop-evolve`. Tienen que aparecer las dos líneas de esa petición, la
  de HTTP y la de `categories.list`, y con números que siguen siendo números.
- El segundo busca en **todos los campos de todas las líneas** el correo y la contraseña del cliente de
  prueba, y la contraseña equivocada con la que se intenta entrar. No puede aparecer ninguno.

Esperan hasta 60 segundos, porque Filebeat envía por lotes y una línea tarda unos segundos en llegar.
Si Elasticsearch no está levantado, **se saltan** en vez de fallar: no es parte de la tienda, y que la
tienda funcione con el sistema de logs caído es justo lo que se buscaba. Leen la clave de `ELASTIC_API_KEY`
en `.env`.

### Por qué tan pocos de cada capa

| Capa | Cuántos | Qué prueba | Coste de un fallo |
|---|---|---|---|
| Backend | 139 | Las reglas: stock, precios, propiedad, migraciones, y lo que dicen los logs | Rápido y señala la línea |
| Frontend | 27 | Los comportamientos que se rompen en silencio | Rápido |
| Extremo a extremo | 17 | Que las piezas están conectadas, y que los logs llegan | Lento, y dice «algo falla» sin decir dónde |

Cuanto más se sube en la tabla, más lentos y más vagos son los mensajes. Por eso arriba hay diecisiete y no
doscientos: aquí solo va lo que **no se puede comprobar de ninguna otra forma**.

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
| `chkp9-update-address` | `003a_addresses` | La página *My account* para editar las dos direcciones | hecho |
| `chkp10-show-address` | `003b_address_history` | El pedido recuerda a qué dirección se envió, porque las direcciones ya no se editan | hecho |
| `chkp11-show-orders` | `003c_orders_user` | Sin sesión no se compra, cada pedido tiene dueño y solo él lo ve | hecho |
| `chkp12-backend-unittest` | ninguna | Tests de los servicios contra una base de datos de pruebas, y tests de lo que los logs no pueden contar | hecho |
| `chkp13-backend-integration` | ninguna | Tests de la API, de la carrera por la última unidad, de las migraciones y de los logs que escriben las rutas | hecho |
| `chkp14-frontend-tests` | ninguna | Tests del frontend sin red, incluido el aviso de producto abierto | hecho |
| `chkp15-e2e-test` | ninguna | Tests de extremo a extremo por HTTP contra la tienda en marcha, y que los logs llegan a Elasticsearch sin secretos | hecho |
| `chkp16-price-history` | `004_price_history` | La tabla del histórico de precios, vacía: todavía nada la rellena ni la lee, así que no hay nada que registrar | hecho |

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

### cp3 · Direcciones de envío y facturación

Cada persona tiene **una dirección de envío y una de facturación**, y se editan en *My account*. El tipo
de dirección es una **columna** de la propia fila, `is_billing`, no una fila en otra tabla de tipos.

8. Guardar las dos direcciones y mirar la tabla: dos filas, una con `is_billing = f` y otra con `t`.

   ```bash
   docker compose exec db psql -U shop -d shop -c "SELECT id, user_id, is_billing, street, city FROM addresses"
   ```

9. Cambiar la dirección de envío y volver a mirar: **la misma fila, con el `id` de antes**. No aparece una
   segunda. Es lo que hace `PUT /me/addresses/shipping`, que fija lo que esa dirección *es*.
10. Intentar meter a mano una segunda dirección de facturación para la misma persona: la base de datos la
    rechaza, porque la regla vive ahí y no en Python.

    ```bash
    docker compose exec db psql -U shop -d shop -c "INSERT INTO addresses (user_id, is_billing, recipient_name, street, city, postal_code) VALUES (1, true, 'X', 'X', 'X', 'X')"
    ```

11. `PUT /me/addresses/home` responde `422` sin que corra nada nuestro: los dos únicos valores posibles
    están declarados en el tipo de la ruta, y salen también en `/docs`.
12. **El `id` de una dirección no aparece en ninguna ruta.** Todo se resuelve desde la sesión, así que no
    hay ningún número que cambiar para llegar a la dirección de otra persona.
13. En Kibana, cada vez que se guarda o se borra una dirección aparece un `user.address.save` o un
    `user.address.delete`. Esta pantalla no ha necesitado ningún log nuevo: todo lo que hace pasa por la
    API, y la API ya lo cuenta. Mirar qué campos llevan: el país sí; la calle, la ciudad, el código postal
    y el nombre no.

> **Otra forma de hacerlo.** También se podrían guardar direcciones sin tipo y decidir en cada pedido cuál
> es la de envío y cuál la de facturación. Aquí se ha elegido la columna a propósito, porque es más fácil de
> leer. Lo que cuesta se ve en el botón *"Copy from shipping"*: usar la misma dirección para las dos cosas
> guarda las mismas líneas dos veces.

### cp3 · El pedido recuerda a dónde se envió

Las direcciones **dejan de editarse**. Cambiar una retira la fila que estaba en uso y escribe otra, así
que la fila a la que apunta un pedido nunca cambia por debajo. Es la lección del precio congelado de
`order_items`, alcanzada por el otro camino: allí copiando el valor, aquí apuntando a una fila que no se
puede modificar.

14. **La demostración**: con sesión iniciada, el carrito muestra *"Shipping to"* con la dirección de
    envío. Comprar, y después **mudarse** cambiando la dirección en *My account*. Volver al pedido: sigue
    diciendo la dirección antigua. La cuenta muestra la nueva.
15. Mirar la tabla: la fila vieja sigue ahí, retirada, y el pedido apunta a ella.

    ```bash
    docker compose exec db psql -U shop -d shop -c "SELECT id, is_active, street, city FROM addresses ORDER BY id"
    ```

    ```bash
    docker compose exec db psql -U shop -d shop -c "SELECT id, shipping_address_id FROM orders"
    ```

16. Lo mismo en Kibana. El `order.create` lleva `shop.shipping_address_id`, y cada `user.address.save`
    lleva `shop.address_id` con el número de la fila nueva. Son el mismo número, así que se puede ver a
    qué dirección fue un pedido sin que la calle aparezca en ningún log. `order.create` lleva también
    el `user.id` de quien compra.
17. Lo que mantiene el orden es un **índice único parcial**: único sobre `(user_id, is_billing)` pero
    **solo** `WHERE is_active`. Cada persona tiene como mucho una de cada en uso y todas las retiradas que
    haga falta. Probar a meter una segunda activa a mano y ver cómo la base de datos la rechaza.
18. `is_active` **no sale en la API**. Que alguien siga usando una dirección es asunto suyo; el pedido
    apunta a una fila concreta y eso no le afecta.
19. La dirección **no se envía desde el navegador**: el servidor la busca a partir del token. Un cliente
    que pudiera nombrar un `id` de dirección sería un cliente capaz de nombrar la de otra persona.
20. El `downgrade` de `003b` fue el segundo que autogenerate no pudo escribir bien: el esquema anterior
    solo admite una dirección por persona y tipo, y para entonces ya hay retiradas. La versión corregida
    borra las retiradas primero **y dice que eso destruye información**, porque el esquema viejo no tiene
    dónde guardarla.

### cp3 · No hay pedidos anónimos

Un pedido pertenece a alguien y solo esa persona puede verlo. Los pedidos aparecen en *My account*.

21. **Dos agujeros que se encontraron probando la API, no leyendo el código.** Antes de este paso,
    `POST /orders` sin token respondía `201`, y peor: `GET /orders/5` **sin token** respondía `200` con el
    correo y la calle del cliente. Cualquiera podía leer todos los pedidos de la tienda contando ids.
    Ahora:

    ```bash
    curl -i -X POST http://localhost:8000/orders -H "X-Cart-Token: TOKEN"
    ```

    Responde `401`. Y el pedido de otra persona responde **`404`, no `403`**: un `403` confirmaría que el
    pedido 42 existe, y eso basta para contar los pedidos del negocio.
22. Pedir con la sesión propia un pedido que es de otra persona, y buscarlo en Kibana. El cliente recibe el
    mismo `404` de siempre, pero el `order.miss` lleva el `user.id` de quien preguntó. Un mismo `user.id`
    con muchos `order.miss` seguidos, cada uno con un `shop.order_id` distinto, es alguien intentando leer
    pedidos ajenos. La respuesta no le dice nada, y el log lo cuenta todo.
23. Un pedido sin dirección también se rechaza, con `409`: tiene que saber a dónde va. En la pantalla el
    botón está deshabilitado antes de llegar ahí, pero la comprobación que manda es la del servidor. En los
    logs sale como `order.create` con `event.outcome: failure` y el motivo en `error.message`.
24. **Lo interesante de la revisión `003c` es lo que NO hace.** No pone `user_id` como `NOT NULL`, porque
    los pedidos anteriores a esta regla no tienen dueño y las únicas salidas serían inventarle uno o
    borrar pedidos de verdad. En su lugar añade la regla como `CHECK ... NOT VALID`:

    ```sql
    ALTER TABLE orders ADD CONSTRAINT ck_orders_user_id_required CHECK (user_id IS NOT NULL) NOT VALID;
    ```

    PostgreSQL la aplica a **todo lo que se escriba a partir de ahora** y no revisa las filas que ya
    estaban. Es la misma técnica con la que se añade una restricción a una tabla enorme sin bloquearla
    durante un recorrido completo; después, cuando las filas viejas están resueltas, se valida con una
    línea: `VALIDATE CONSTRAINT`. Se puede ver funcionando:

    ```bash
    docker compose exec db psql -U shop -d shop -c "INSERT INTO orders (customer_email, total_cents) VALUES ('x@x.com', 100)"
    ```

25. `customer_email` se mantiene aunque ya se sepa quién compra: guarda el correo **del día del pedido**,
    congelado como el precio y la dirección. Cambiar el correo de la cuenta el año que viene no debe
    reescribir a dónde se confirmó un pedido antiguo.

## Fuera de alcance

Se dejan fuera a propósito (no se implementan):

- Pasarela de pago (un pedido nace ya en estado `paid`)
- Roles y permisos
- Imágenes de producción (los contenedores de la aplicación arrancan los servidores de desarrollo)
- CI (los tests se ejecutan a mano antes de cada tag)

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
| `startup` / `shutdown` | info | El servidor arranca / se para limpiamente | — |
| `categories.empty` | warning | `GET /categories` sin ninguna categoría | — |
| `cart.create` | info | `POST /cart` | `shop.cart_ref` y el resumen del carrito |
| `cart.miss` | warning | Un token de carrito que no existe | `shop.cart_ref` |
| `cart.item.set` | info / warning | `PUT /cart/items/{id}`, bien (`success`) o sin stock (`failure`) | `shop.product_id`, `shop.quantity`, `error.message` si falla, y el resumen del carrito |
| `cart.item.remove` | info | `DELETE /cart/items/{id}` | `shop.product_id` y el resumen del carrito |
| `order.create` | info / warning | `POST /orders`, hecho (`success`) o rechazado (`failure`) | `shop.order_id`, `shop.order_total_cents`, `shop.order_lines`, `shop.order_units`, `shop.product_ids`, `shop.cart_ref`, `shop.shipping_address_id`, `user.id`, `error.message` si falla |
| `order.list` | info | `GET /orders`, los pedidos de quien pregunta | `user.id`, `shop.orders_returned` |
| `order.miss` | warning | `GET /orders/{id}` que no existe o que es de otra persona | `user.id`, `shop.order_id` |
| `user.register` | info / warning | `POST /users`, hecho o con el correo ya registrado | `user.id` si sale bien, `event.reason: email_taken` si no |
| `user.login` | info / warning | `POST /login`, dentro o fuera | `user.id` y `shop.session_ref` si entra; `event.reason` (`wrong_password` o `unknown_email`) y `user.id` o `shop.email_ref` si no |
| `user.session` | info | Un token de sesión caducado o inventado (`401`) | `shop.session_ref` |
| `user.logout` | info | `POST /logout` | `shop.session_ref` |
| `user.address.save` | info | `PUT /me/addresses/{kind}` | `user.id`, `shop.address_kind` (`shipping` o `billing`), `shop.address_country`, `shop.address_id` (la fila nueva) |
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
