# Bot de ventas de Vinted/Wallapop por WhatsApp

Servicio self-hosted que escucha un grupo cerrado de WhatsApp, lee las etiquetas
de envío (PDF), las capturas de venta y las notas que mandan los administradores,
saca los datos con un LLM y los guarda en un SQLite local. Después contesta en el
mismo grupo con el resumen de lo que ha registrado.

> Este proyecto es independiente del resto del repositorio (la PWA retirada de la
> raíz). Es autocontenido: se puede mover a otro repo tal cual.

```
   Móvil admin                Servidor local (docker compose)
  ┌───────────┐      ┌──────────────────────────────────────────────┐
  │  Grupo de │      │  evolution-api ──webhook──▶ bot (FastAPI)     │
  │  ventas   │◀────▶│      │                        │              │
  │ (WhatsApp)│      │      │                   ┌────┴─────┐        │
  └───────────┘      │      │                   │ pdfplumber│       │
        ▲            │      │                   │ pdf2image │       │
        │            │  postgres + redis        └────┬─────┘        │
        │            │  (estado del gateway)         │              │
        │            │                          LLM (Claude/Gemini/ │
        │            │                               Ollama)        │
        │            │                               │              │
        └────respuesta del bot──────────────── ventas.db (SQLite)   │
                     └──────────────────────────────────────────────┘
```

El número de la SIM secundaria se vincula al gateway como **dispositivo
vinculado** (multi-dispositivo). El móvil principal de esa SIM puede seguir
usándose con normalidad.

---

## 1. Requisitos

- Docker y Docker Compose v2 **en la máquina donde vaya a correr**. El bot es un
  servicio permanente: si lo levantas en un portátil que se apaga, deja de
  registrar ventas mientras esté apagado.
- Una SIM secundaria con WhatsApp ya instalado y funcionando en un móvil.
- Un grupo de WhatsApp con los administradores **y el número secundario dentro**.
- Una clave de API del proveedor de IA (por defecto Anthropic) o un Ollama con
  visión si lo quieres todo en local.

## 2. Puesta en marcha

### Paso 1 — Configuración

```bash
cd whatsapp-ventas
cp .env.example .env
openssl rand -hex 24   # genera uno para POSTGRES_PASSWORD
openssl rand -hex 24   # otro para EVOLUTION_API_KEY
openssl rand -hex 24   # otro para WEBHOOK_TOKEN
```

Edita `.env` y rellena esos tres secretos y `ANTHROPIC_API_KEY`.
**Deja `GRUPO_VENTAS_JID` vacío de momento**: lo sacamos en el paso 4. Mientras
esté vacío el bot no procesa ningún mensaje, que es justo lo que queremos hasta
haberlo blindado.

### Paso 2 — Levantar la pila

```bash
# el contenedor corre como uid 10001, así que la carpeta de datos tiene que ser suya
mkdir -p datos && sudo chown 10001:10001 datos

docker compose up -d --build
docker compose ps          # los cuatro servicios en estado "running"
curl -s localhost:8000/salud | python3 -m json.tool
```

Si `datos/` se queda en manos de root, SQLite no podrá escribir y el bot
registrará un error en cada mensaje; el `chown` de arriba lo evita.

`/salud` avisa de lo que falta por configurar en `problemas_configuracion`.

### Paso 3 — Vincular la SIM secundaria (QR)

```bash
docker compose exec bot python -m tools.gestion crear
```

El comando crea la instancia y devuelve el QR:

- Guarda `qr.png` dentro del contenedor; para verlo desde el host:
  `docker compose cp bot:/srv/qr.png .` y ábrelo.
- Si tienes instalado `qrcode` (`pip install qrcode`) lo pinta directamente en el
  terminal.

**En el móvil de la SIM secundaria** (no en el tuyo):
WhatsApp → **Ajustes** → **Dispositivos vinculados** → **Vincular un
dispositivo** → escanea el QR.

El QR caduca en unos 40 segundos. Si se te pasa:

```bash
docker compose exec bot python -m tools.gestion qr
docker compose exec bot python -m tools.gestion estado   # debe decir "open"
```

> El móvil de la SIM secundaria tiene que conectarse a internet de vez en cuando
> o WhatsApp cerrará la sesión vinculada (política de ~14 días).

### Paso 4 — Sacar el `group_jid` y blindar el bot

Con el número ya dentro del grupo de ventas:

```bash
docker compose exec bot python -m tools.gestion grupos
```

```
GROUP_JID                         NOMBRE
120363041234567890@g.us           Ventas Vinted/Wallapop
120363049876543210@g.us           Familia
```

Copia el JID que acaba en `@g.us` del grupo correcto a `.env`:

```
GRUPO_VENTAS_JID=120363041234567890@g.us
```

y reinicia el backend:

```bash
docker compose up -d bot
curl -s localhost:8000/salud | python3 -m json.tool   # "chats_vigilados" con tu grupo
```

A partir de aquí, cualquier mensaje que no venga de ese JID se descarta antes de
mirarlo siquiera: no se descarga el adjunto, no se llama al LLM y no se guarda
nada. Los chats privados del número quedan fuera.

### Paso 5 — Apuntar el webhook al backend

```bash
docker compose exec bot python -m tools.gestion webhook
```

Configura la instancia para que mande solo `MESSAGES_UPSERT` a
`http://bot:8000/webhook/<WEBHOOK_TOKEN>`, con el adjunto ya en base64 (así el
backend casi nunca tiene que volver a pedirlo).

### Paso 6 — Prueba de humo

```bash
docker compose exec bot python -m tools.gestion probar
```

Debe aparecer un mensaje del bot en el grupo. Ahora escribe tú en el grupo:

```
Vendida la chaqueta vaquera Levi's talla S por 25€ en Vinted
```

y el bot debería contestar:

```
✅ Venta registrada #1
🛍️ Artículo: Chaqueta vaquera Levi's talla S
🏷️ Plataforma: Vinted
💶 Precio: 25,00 €
📦 Transportista: —
🔖 Seguimiento: —
📍 Destino: —
📌 Estado: ⏳ pendiente de envío
🕐 07/09/2026 18:42
```

Prueba luego a soltar una etiqueta en PDF y una captura de la app.

---

## 3. Uso desde el grupo

Manda al grupo lo que sea y el bot lo registra solo:

| Qué mandas | Qué hace |
|---|---|
| PDF de etiqueta | Lee la capa de texto; si no la tiene, lo manda al modelo con visión |
| Captura de la venta | Inferencia multimodal |
| Nota de texto | Extracción directa |
| Foto con pie de foto | Usa el pie como contexto (ahí suele estar el precio) |

Comandos:

| Comando | Qué hace |
|---|---|
| `/pendientes` | Ventas sin enviar |
| `/enviado #12` o `/enviado <código>` | Marca como enviada |
| `/entregado <ref>` / `/cancelado <ref>` | Otros estados |
| `/resumen` | Totales e ingresos acumulados |
| `/ayuda` | Chuleta |

**Fusión automática:** si la captura de la venta y la etiqueta llegan por
separado pero comparten código de seguimiento, se fusionan en un único pedido
(el bot responde «🔄 Venta actualizada» en vez de crear otra fila).

---

## 4. Cómo se evitan los códigos de seguimiento inventados

Es el problema real de este montaje: un artículo mal transcrito se corrige
leyendo el chat, pero un tracking alucinado hace que des por enviado un paquete
que no existe. Hay tres capas:

1. **Prompt** (`app/prompts.py`): reglas duras y seis ejemplos, la mitad de ellos
   con la respuesta correcta siendo `null` (código borroso, captura sin tracking,
   nota sin código). Se le enseña explícitamente que el número del Punto Pack, el
   código postal, el teléfono y el número de pedido **no** son el tracking.
2. **Verificación literal** (`app/validacion.py`): cuando tenemos el texto real
   del documento —PDF con capa de texto, o una nota escrita en el chat— se exige
   que el código devuelto aparezca *literalmente* ahí (comparando sin espacios ni
   guiones). Si no aparece, se descarta y se avisa en el grupo. Es la capa que
   más pesa, porque la mayoría de etiquetas de Vinted/Wallapop son PDFs con texto.
3. **Formato conocido**: si no hay texto contra el que verificar (una captura, una
   etiqueta escaneada) se comprueba que el código encaje con la forma de algún
   transportista real. Si no encaja se guarda igual, pero marcado con
   «compruébalo a mano», y si el formato contradice al transportista detectado
   también se dice.

Además: la fecha nunca la pone el modelo (se toma del timestamp del mensaje), los
precios absurdos se descartan, y si el modelo devuelve uno de los códigos de
ejemplo del prompt se detecta como copia y se tira.

Cuando algo se descarta, el bot lo dice en el grupo con un `⚠️` en vez de callarse.

---

## 5. Base de datos

`./datos/ventas.db` en el host (montado en `/datos` dentro del contenedor).

```sql
CREATE TABLE ventas (
    id, fecha_registro, articulo, plataforma, precio_venta, transportista,
    codigo_seguimiento, codigo_norm, destinatario_o_punto_pack,
    estado,            -- pendiente_envio | enviado | entregado | cancelado
    confianza, origen, tipo_documento, mensaje_id, remitente, avisos,
    creado_en, actualizado_en
);
CREATE TABLE mensajes_procesados (mensaje_id, procesado_en, resultado);
```

`mensajes_procesados` es lo que hace el webhook idempotente: Evolution reintenta
las entregas y sin esta tabla pagarías el LLM dos veces por el mismo mensaje.

```bash
# consultas rápidas
sqlite3 datos/ventas.db "SELECT id, fecha_registro, articulo, precio_venta, estado FROM ventas ORDER BY id DESC LIMIT 10;"
sqlite3 datos/ventas.db "SELECT strftime('%Y-%m', fecha_registro) mes, COUNT(*), ROUND(SUM(precio_venta),2) FROM ventas GROUP BY 1;"

# copia de seguridad en caliente
sqlite3 datos/ventas.db ".backup 'datos/ventas-$(date +%F).db'"

# exportar a CSV (para subirlo a Sheets si te hace falta)
sqlite3 -header -csv datos/ventas.db "SELECT * FROM ventas;" > ventas.csv
```

## 6. API HTTP

Escucha en `127.0.0.1:8000`:

| Método y ruta | Para qué |
|---|---|
| `POST /webhook/{token}` | Lo que llama Evolution API |
| `GET /salud` | Estado, cola, configuración pendiente y totales |
| `GET /ventas?estado=&limite=&desplazamiento=` | Listado |
| `GET /ventas/{id}` | Una venta |
| `POST /ventas/{id}/estado?estado=enviado` | Cambiar estado |

El webhook contesta enseguida y encola: la extracción tarda segundos y no
queremos que el gateway reintente por timeout.

## 7. Variables de configuración

Todas van en `.env` (ver `.env.example`). Las que más se tocan:

| Variable | Por defecto | Qué hace |
|---|---|---|
| `GRUPO_VENTAS_JID` | *(vacío)* | Único chat que se escucha. Vacío = no escucha nada |
| `WEBHOOK_TOKEN` | *(vacío)* | Token en la URL del webhook |
| `LLM_PROVEEDOR` | `anthropic` | `anthropic`, `gemini` u `ollama` |
| `MODELO_TEXTO` | `claude-haiku-4-5` | Para notas y PDFs con capa de texto |
| `MODELO_VISION` | `claude-sonnet-5` | Para imágenes y PDFs escaneados |
| `PDF_NATIVO` | `true` | PDF entero al modelo vs. rasterizar con poppler |
| `PDF_MIN_CARACTERES` | `80` | Menos texto que esto = etiqueta escaneada |
| `MAX_MEDIA_MB` | `20` | Tope de tamaño de adjunto |
| `RESPONDER_ERRORES` | `true` | Avisar en el grupo cuando algo no se puede leer |
| `COMANDOS_ACTIVOS` | `true` | Habilita `/pendientes`, `/enviado`… |

### Todo en local, sin API de pago

```
LLM_PROVEEDOR=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODELO=llama3.2-vision
PDF_NATIVO=false        # Ollama no lee PDFs: hay que rasterizar
```

Añade un servicio `ollama` al compose en la red `interna`. Los modelos locales de
visión leen bastante peor los códigos de barras: la verificación literal contra
el texto del PDF pasa a ser aún más importante.

### Coste aproximado (Anthropic, precios de referencia)

Órdenes de magnitud, no una factura: el prompt de sistema ronda 1,3k tokens y la
respuesta unos 200.

- Nota o PDF con texto (Haiku 4.5, 1 $/5 $ por millón): del orden de **0,2–0,3
  céntimos** por mensaje.
- Captura o etiqueta escaneada (Sonnet 5, 2 $/10 $ por millón): del orden de
  **0,8–1 céntimo** por mensaje.

Es decir, unos pocos euros al mes para cientos de ventas. El prompt de sistema va
marcado para caché, así que en ráfagas sale más barato todavía.

## 8. Operación

```bash
docker compose logs -f bot            # log del backend
docker compose logs -f evolution-api  # log del gateway (desconexiones, QR)
docker compose restart bot            # recargar tras tocar el .env
docker compose exec bot python -m tools.gestion estado
```

Si WhatsApp cierra la sesión (móvil mucho tiempo sin conexión, sesión revocada a
mano), vuelve al **paso 3**: `tools.gestion qr` y escanear otra vez. Ni la base de
datos ni el webhook se pierden.

## 9. Problemas frecuentes

| Síntoma | Causa habitual |
|---|---|
| El bot no responde a nada | `GRUPO_VENTAS_JID` mal o vacío. Míralo en `/salud` → `chats_vigilados` |
| `/salud` dice `problemas_configuracion` | Falta un secreto en el `.env` |
| El grupo no sale en `gestion grupos` | El número secundario no está dentro del grupo, o la instancia no está `open` |
| Llegan mensajes pero no hay respuesta | Mira `docker compose logs bot`: suele ser la clave del LLM |
| «No he podido registrar esto» siempre con PDFs | Etiquetas escaneadas + `PDF_NATIVO=false` sin poppler. Ponlo a `true` o revisa la imagen |
| El bot se contesta a sí mismo | No debería: se ignoran los mensajes con `fromMe`. Si pasa, revisa que no haya dos instancias con el mismo webhook |
| Ventas duplicadas | Solo se fusionan por código de seguimiento; dos capturas sin código son dos ventas distintas |

## 10. Pruebas

```bash
python -m venv venv && ./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest
```

101 pruebas, todas sin red: dobles del gateway y del LLM, PDFs generados al vuelo.
Cubren el blindaje por grupo (incluido que el JID vacío deja al bot sordo), la
idempotencia, las tres vías de extracción (texto/PDF/imagen), el descarte de
códigos inventados, la fusión por tracking, los comandos, la autenticación del
webhook, el rescate del base64 en mensajes envueltos y los tres formatos de
`webhook/set`, y el puente con Glivo (la funcion que escribe se inyecta,
asi que ninguna prueba toca la base de nadie).

## 11. Seguridad

- Ni el gateway ni el backend se publican en `0.0.0.0`, solo en `127.0.0.1`. Si
  necesitas alcanzarlos desde fuera, pon un proxy inverso con TLS delante.
- El webhook exige un token en la ruta y compara en tiempo constante.
- El bot solo lee un chat. Los mensajes privados del número secundario no se
  procesan ni se descargan.
- Las etiquetas llevan nombre y dirección del comprador: son datos personales.
  Se guardan en tu servidor y, con Anthropic o Gemini, se envían al proveedor
  para extraerlos. Si eso no te vale, usa Ollama y no sale nada de la máquina.
- Haz copia de `datos/ventas.db` (la del gateway, en volúmenes de Docker, se
  puede regenerar volviendo a escanear el QR).

## 12. Limitaciones conocidas

- Un único grupo por instancia (a propósito: es el blindaje).
- No se leen álbumes de varias fotos como una sola venta; cada imagen va por
  separado.
- El estado se cambia a mano con `/enviado`; no hay seguimiento automático contra
  las webs de los transportistas.
- WhatsApp Business API oficial no está soportada; esto usa la vía de dispositivo
  vinculado, que es lo que permite un número normal.

## 12b. Enganche con Glivo (el bot de Telegram)

Claudio ya registraba ventas por Telegram escribiendo `Registro: ...`, y eso
va a la tabla `eventos_diarios` de `/home/claudio/glivo/glivo_memory.db`, que
es lo que leen el panel de El Sistema y `experto_vinted.py`. Si este bot se
quedara solo con su `ventas.db` habría **dos contabilidades**, y el experto de
Vinted analizaría la mitad de las ventas.

`tools/puente_glivo.py` lo arregla: lee las ventas del bot por su API y las
apunta en Glivo con `registro_diario.guardar_evento()`.

```bash
# ver qué haría, sin escribir nada
cd /home/claudio/glivo && ./.venv/bin/python   /home/claudio/sistema/whatsapp-ventas/tools/puente_glivo.py --simular

# apuntarlas de verdad
cd /home/claudio/glivo && ./.venv/bin/python   /home/claudio/sistema/whatsapp-ventas/tools/puente_glivo.py
```

Decisiones que conviene conocer antes de tocarlo:

- **Corre en el host, no en el contenedor**, porque `registro_diario` vive en
  el entorno de Glivo. No modifica ni un fichero de Glivo: solo llama a su
  función pública.
- **Lee por HTTP, no abriendo `ventas.db`.** La base es del uid 10001 y el
  puente corre como `claudio`: al abrirla salta
  `attempt to write a readonly database` incluso en un SELECT, porque una base
  en WAL necesita sus ficheros auxiliares hasta para leer.
- **Las ventas sin precio no se apuntan.** Un evento de venta sin importe abre
  una `venta_pendiente` en Glivo y te pregunta el importe por Telegram — justo
  el trabajo manual que el bot viene a quitar. Entran cuando llega el precio.
- **Comprueba el `-1`.** `guardar_evento()` falla en silencio devolviendo -1;
  si eso pasa, la venta no se marca y se reintenta en la pasada siguiente.
- **No duplica**: los ids ya apuntados se guardan en `datos/puente_glivo.json`.
  Cada apunte lleva `[bot ventas #<id>]` al final del texto, para reconocerlos.

Para deshacerlo: borra el script y `datos/puente_glivo.json`.

## 13. Qué está verificado y qué no (07/09/2026)

Distinción importante antes de fiarse de nada de lo de arriba.

**Verificado sin red:** 89 pruebas en verde (`python -m pytest`), el YAML del
compose bien formado, y el arranque real del backend con uvicorn (webhook,
token y trabajador en segundo plano).

**Sin verificar nunca:** todo lo que toca WhatsApp o Evolution de verdad. Ni una
sola etiqueta real ha pasado por aquí. En concreto, siguen sin calibrar con
material real:

- Los patrones de `app/validacion.py`. Son heurísticas escritas sin etiquetas
  delante y **los rangos se solapan**: un código de 10 a 13 dígitos encaja a la
  vez con SEUR, GLS, CTT, Correos Express, Boyacá o DHL, así que la capa 3 no
  puede decidir sola y pide comprobación a mano. Eso no es un fallo —es el lado
  seguro—, pero con etiquetas reales delante conviene afinar los rangos para que
  el aviso deje de saltar siempre. Un aviso que salta siempre deja de leerse.
- `PDF_MIN_CARACTERES=80`, el umbral que decide si un PDF va por texto o por
  visión. Nunca se ha probado contra una etiqueta escaneada de verdad.
- La forma exacta del payload del webhook de tu Evolution. `_extraer_base64`
  mira ahora todas las capas del mensaje, pero si aun así el bot acaba pidiendo
  cada adjunto por `getBase64FromMediaMessage`, arranca con `LOG_LEVEL=DEBUG`,
  mira el payload crudo y añade la ruta que falte.

Al montarlo por primera vez, el paso 5 (`tools.gestion webhook`) prueba tres
formatos de cuerpo distintos y luego **relee la configuración** para confirmar
que el base64 quedó encendido: un cuerpo con la clave equivocada puede devolver
200 y dejarlo apagado.
