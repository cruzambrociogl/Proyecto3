# Protocolo PHY Chat — especificación completa (v6b)

Proyecto 03, Capa Física No Convencional. Este documento reúne todo el protocolo diseñado: canales, símbolo, matriz, frame, mensaje, colas y vida del enlace.

- **Estado:** diseño aceptado por el profesor el 2026-11-14 ("hasta demasiado complejo, pero está bien"). Toda la evaluación es a 1 Hz.
- **Qué está construido:** el chat, el frame, el CRC-8, ACK/NACK y el enlace existen en el código (versión v2, con otro line coding). La matriz, los tres tipos de lectura y las colas completas todavía no. Ver [sección 14](#14-estado-de-implementación).
- **Tiempo:** el diseño ignora a propósito el costo en tiempo. Las optimizaciones están en la [sección 15](#15-puntos-abiertos-y-optimizaciones-pendientes).
- **Historia y decisiones:** [design-log.md](design-log.md). Versión en tablas para el profesor: [matrix_v6b_es.csv](matrix_v6b_es.csv).

Lo marcado como **(propuesto)** es un detalle que todavía no se ha confirmado con nadie; el resto es lo que se le mostró al profesor.

---

## 1. Idea general

- Dos equipos (BeagleBone) con un chat web bidireccional.
- Cada sentido tiene **5 canales físicos propios**: `CLK`, `D0`, `D1`, `P`, `Q`.
- Medio byte (4 bits) viaja como **una matriz de 5 ticks × 4 canales**.
  - Las filas son ticks: la parte **serial**.
  - Las columnas son canales que se envían al mismo tiempo: la parte **paralela**.
- Cada canal de datos lleva los 4 bits con una mezcla XOR distinta, así que **basta con que sobreviva un canal**.
- Los bits se validan durante la transmisión con tres familias de ecuaciones XOR: horizontal, diagonal y vertical.
- El CRC-8 del frame y el ACK/NACK quedan como última red.

### Capas

```
Aplicación     chat web + LOG
Presentación   UTF-8 (1 a 4 bytes) o Extended ASCII
Mensaje        START, un DATA por byte, END
Enlace         colas con prioridad, stop-and-wait, ACK/NACK, SEQ, CRC-8
Frame          SYN | SFD | CTRL | DATA | CRC | SEQ = 40 bits = 10 matrices
Matriz         4 bits -> 5 ticks x 4 canales, con validación horizontal, diagonal y vertical
Símbolo        4 lecturas por tick: válido, bloqueado o ruidoso
Medio          luz, sonido, etc. Cada canal termina como un 0/1 en un pin
```

### Unidades

```
lectura  <  tick (4 lecturas)  <  matriz (5 ticks)  <  frame (10 matrices)  <  mensaje (bytes + 2 frames)
```

| Unidad | Contiene | Duración |
|---|---|---|
| Lectura | una muestra del sensor (0 o 1) | un cuarto de tick |
| Tick | 4 lecturas por canal = una fila de la matriz | 1 s a 1 Hz |
| Matriz | 5 ticks × 4 canales = 20 celdas = 4 bits de datos | 5 ticks |
| Frame | 10 matrices = 40 bits | 50 ticks |
| Mensaje | START + un DATA por byte + END | (bytes + 2) frames |

---

## 2. Canales

| Canal | Función | Interferencia |
|---|---|---|
| `CLK` | marca cada tick y el inicio de cada matriz | nunca se interfiere (regla del profesor) |
| `D0` | los 4 bits en orden | puede ser bloqueado o ruidoso |
| `D1` | los 4 bits corridos un tick; viaja **invertido** | igual |
| `P` | `D0 ^ D1` en cada tick | igual |
| `Q` | mezcla diagonal de `D0` y `P` | igual |

- Son 5 canales por sentido y 10 en total. Cada sentido tiene su propio `CLK`.
- Los dos sentidos no comparten nada en el medio: ambos equipos pueden enviar al mismo tiempo.
- En reposo todos los emisores están apagados (nivel 0) y el `CLK` está en silencio.
- Asignación de medios **(propuesto, depende de las piezas)**: `CLK` y `D0` en láser, `D1` y `P` en IR, `Q` en sonido. Así una mano que tapa toda la luz deja vivo el canal de sonido.

---

## 3. Símbolo: un tick

Cada tick se divide en 4 cuartos. El emisor mantiene un nivel por cuarto y el receptor lee cada canal 4 veces, una al centro de cada cuarto.

| Patrón de 4 lecturas | Significado |
|---|---|
| `0 0 1 1` | bit 1 |
| `1 1 0 0` | bit 0 |
| `0 0 0 0` | **bloqueado** (mano entre emisor y sensor) |
| `1 1 1 1` | **bloqueado** (sensor saturado, puntero IR) |
| cualquier otro | **ruidoso** (parpadeo, ruido) |

Reglas:

1. Un tick bloqueado o ruidoso es una celda **desconocida** (`E`).
2. Si un canal mostró **ruido** en algún tick de una matriz, **no se le cree en toda esa matriz**: todas sus celdas pasan a desconocidas, aunque algún tick pareciera válido.
3. Un canal que solo estuvo **bloqueado** conserva sus ticks buenos.
4. `D1` viaja invertido: el emisor invierte el bit antes de enviarlo y el receptor lo invierte de nuevo antes de validar. Sin esto, la matriz de puros ceros sería válida y la misma interferencia en los 4 sensores podría pasar como dato.

### El CLK

| Patrón | Significado |
|---|---|
| `1 1 0 0` | tick normal |
| `1 0 1 0` | tick 0: inicio de matriz (doble parpadeo) |
| silencio | no hay transmisión |

El receptor toma el ritmo del `CLK` que recibe, no de su propio reloj. Por eso los dos sentidos pueden ir a frecuencias distintas.

---

## 4. La matriz

Los 4 bits son `a b c d`, con `a` el más significativo. Cada celda tiene una receta fija:

```
            D0        D1       P        Q
  tick 0    a         b        a^b      a^b^c
  tick 1    b         c        b^c      b^c^d
  tick 2    c         d        c^d      a^b^c^d
  tick 3    d         a^b      a^b^d    a^c^d
  tick 4    a^b^c^d   a^c^d    b        a^b^d      <- validación vertical
```

### Las tres validaciones

Todas son XOR y deben dar par.

| Validación | Regla | Cuándo se revisa |
|---|---|---|
| Horizontal | `P[t] = D0[t] ^ D1[t]` | en cada tick, incluido el tick 4 |
| Diagonal | `D1[t] = D0[t+1]` y `Q[t] = D0[t] ^ P[t+1]`, para t = 0, 1, 2 | en cada tick desde el tick 1 |
| Vertical | celda del tick 4 = XOR de las 4 celdas de arriba del mismo canal | en el tick 4 |

### De dónde salen las recetas

Las columnas son ventanas de una sola secuencia `s[k+4] = s[k] ^ s[k+1]` que empieza con `a, b, c, d`:

```
s0=a  s1=b  s2=c  s3=d  s4=a^b  s5=b^c  s6=c^d  s7=a^b^d  s8=a^c  s9=b^d
s10=a^b^c  s11=b^c^d  s12=a^b^c^d  s13=a^c^d  s14=a^d   (se repite cada 15)
```

- `D0` empieza en `s0`, `D1` en `s1`, `P` en `s4` y `Q` en `s10`.
- Cada columna son 4 términos seguidos más su XOR.
- Cuatro términos seguidos de esta secuencia siempre determinan `a b c d`: por eso un solo canal basta.

### Ejemplo: 'h' = `0110 1000`

Un byte son dos matrices, primero la mitad alta.

```
  0110          D0  D1  P   Q          1000          D0  D1  P   Q
  tick 0        0   1   1   0          tick 0        1   0   1   1
  tick 1        1   1   0   0          tick 1        0   0   0   0
  tick 2        1   0   1   0          tick 2        0   0   0   1
  tick 3        0   1   1   1          tick 3        0   1   1   1
  tick 4        0   1   1   1          tick 4        1   1   0   1
```

Lo que viaja por los canales para `0110` (4 lecturas por tick; `D1` ya invertido):

| Canal | Tick 0 | Tick 1 | Tick 2 | Tick 3 | Tick 4 | Bits de la matriz |
|---|---|---|---|---|---|---|
| CLK | `1 0 1 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | inicio de matriz en tick 0 |
| D0 | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 0 1 1 0 0 |
| D1 | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 1 1 0 1 1 (viaja 0 0 1 0 0) |
| P | `0 0 1 1` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `0 0 1 1` | 1 0 1 1 1 |
| Q | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | 0 0 0 1 1 |

La tabla de las 16 matrices está en el [anexo](#anexo-las-16-matrices).

---

## 5. Cómo decide el receptor

Al terminar el tick 4 el receptor tiene 20 celdas: cada una es 0, 1 o desconocida.

1. **Marcar lo desconocido.** Ticks bloqueados o ruidosos, y todas las celdas de un canal que mostró ruido ([sección 3](#3-símbolo-un-tick)).
2. **Resolver.** Cada celda conocida es una ecuación XOR en `a, b, c, d`. En la práctica se comparan las celdas conocidas contra las 16 matrices posibles.
   - **Una sola matriz coincide en todo:** se acepta. Si había celdas desconocidas, quedó *reconstruida*.
   - **Más de una coincide:** no llegó suficiente información. La matriz queda **perdida** (y se sabe que está perdida).
   - **Ninguna coincide:** algún canal miente. Sigue el paso 3.
3. **Corregir mentiras.**
   - *Pocos bits mentirosos:* se toma la matriz más cercana solo si está dentro del radio seguro. Sea `gap` la menor cantidad de celdas conocidas en que difieren dos matrices válidas y `e` las diferencias con la más cercana: se acepta si `2·e < gap` y es la única a esa distancia.
   - *Un canal completo mintiendo:* se descarta cada canal por turno. Si lo que queda coincide con una sola matriz, y solo una matriz aparece entre todas las pruebas, se acepta.
   - *Si no:* la matriz queda **detectada como mala** y se trata como perdida.
4. **Matriz perdida:** el frame no se puede completar. Se guardan las celdas buenas ([sección 8](#8-enlace-ack-nack-y-retransmisión)) y se responde NACK.

### Qué tan rápido se conoce el medio byte

- Con los 4 canales vivos: el tick 0 da `a, b, c` y el tick 1 da `d`. Se conoce en **2 ticks**; los otros 3 solo confirman.
- Con un solo canal vivo: se conoce en **4 ticks**.

Más canales vivos = dato antes. Esa es la parte híbrida.

---

## 6. Casos

### A. Un bit mentiroso (parpadeo en `D1`, tick 2: lee 1 en vez de 0)

```
            D0  D1  P   Q
  tick 0    0   1   1   0
  tick 1    1   1   0   0
  tick 2    1  [1]  1   0    falla horizontal: 1^1 = 0 pero P = 1      -> indica la fila
  tick 3    0   1   1   1    falla diagonal:   D1[2] = 1 pero D0[3] = 0
  tick 4    0   1   1   1    falla vertical de D1: 1^1^1^1 = 0 pero V = 1 -> indica la columna
```

El cruce de la fila (tick 2) con la columna (`D1`) es el mentiroso. Se invierte a 0.

### B. Mano sobre `D0`, `D1` y `P` toda la matriz (solo `Q` vivo)

```
            D0  D1  P   Q
  tick 0    E   E   E   0     a^b^c   = 0
  tick 1    E   E   E   0     b^c^d   = 0
  tick 2    E   E   E   0     a^b^c^d = 0    con tick 0: d = 0; con tick 1: a = 0
  tick 3    E   E   E   1     a^c^d   = 1    c = 1; el tick 1 da b = 1
  tick 4    E   E   E   1     validación
```

Resultado: `0 1 1 0`, correcto y sin retransmisión.

### C. El último canal también pierde un tick

`Q` lee `0 E 0 1 1`. El tick perdido es el XOR de los otros cuatro: `0^0^1^1 = 0`. Después se resuelve como en B.

### D. El último canal pierde dos ticks

`Q` lee `0 E E 1 1`. Quedan 3 ecuaciones para 4 bits: `0110` y `0001` cumplen las dos. El receptor **no adivina**: guarda las 3 celdas buenas y responde NACK. Una sola celda buena más de la repetición decide (por ejemplo `Q` en el tick 1 es 0 para `0110` y 1 para `0001`).

---

## 7. Frame

Es el frame del enunciado. La matriz no lo cambia: solo es la forma en que sus bits viajan.

| Campo | Bits | Contenido |
|---|---|---|
| SYN | 8 | `1010 1010` (estabiliza el medio) |
| SFD | 8 | `B3` = `1011 0011` (inicio del frame) |
| CTRL | 4 | tipo de frame |
| DATA | 8 | un byte |
| CRC | 8 | CRC-8 sobre dos bytes: `(CTRL << 4) | SEQ` y `DATA` |
| SEQ | 4 | número de secuencia, 0 a 15 |

Los 40 bits se envían del más significativo al menos significativo, 4 bits por matriz:

```
  matriz   0    1    2    3    4     5    6    7    8    9
  campo    SYN  SYN  SFD  SFD  CTRL  DATA DATA CRC  CRC  SEQ
```

Ejemplo: DATA con 'h' (`68`), SEQ 1 y CRC-8/SMBUS (`5D`) son los medios bytes `A A B 3 1 6 8 5 D 1`.

| CTRL | Nombre | DATA |
|---|---|---|
| 1 | DATA | un byte del texto |
| 2 | ACK | reporte de canales (bits 3 a 0) |
| 3 | NACK | reporte de canales (bits 3 a 0) **(propuesto)** |
| 4 | START | id del encoding |
| 5 | END | cantidad de bytes del mensaje mod 256 |
| 6 | PING | CRC-8 del equipo (bits 7 y 6) + reporte de canales (bits 3 a 0) |
| 7 | PONG | igual que PING |

**CRC-8 seleccionable:** SMBUS (id 0), AUTOSAR (1), SAE-J1850 (2), MAXIM-DOW (3). PING y PONG siempre se validan con SMBUS, para que los equipos se puedan leer aunque tengan configuraciones distintas.

**Inicio del frame (propuesto):** el `CLK` está en silencio entre frames, y como nunca se interfiere, el primer tick después de un silencio es el tick 0 de la matriz 0. SYN y SFD lo confirman cuando se pueden resolver.

---

## 8. Enlace: ACK, NACK y retransmisión

1. **Stop-and-wait.** Cada frame START, DATA o END espera su ACK antes de que salga el siguiente.
2. **ACK.** El receptor responde ACK con el mismo SEQ cuando el frame se completa y el CRC-8 pasa.
3. **NACK.** El receptor responde NACK cuando una matriz quedó perdida o el CRC-8 falla.
4. **Timeout.** Si no llega ACK ni NACK en 2 tiempos de frame, el emisor repite el frame. El otro equipo puede estar a medio frame propio antes de responder.
5. **Retransmisión.** Se repite el frame completo. Máximo 8 reintentos; después el frame pasa a FAILED.
6. **Duplicados.** Si se pierde un ACK y llega un frame repetido (mismo SEQ), el receptor lo descarta y vuelve a enviar el ACK. START siempre abre un mensaje nuevo y nunca se trata como duplicado.
7. **Reparación.** El receptor conserva las celdas buenas de un frame que falló. Cuando llega la repetición **(regla propuesta)**:
   - si una matriz de la repetición se resuelve sola, se usa esa;
   - si no, se juntan las celdas conocidas de las dos copias y se resuelve de nuevo; si las dos copias se contradicen en alguna celda, se descartan las celdas guardadas;
   - el CRC-8 del frame decide al final. Lo guardado se borra cuando un frame se acepta.
8. **Reporte de canales.** ACK, NACK, PING y PONG llevan 4 bits, uno por canal: bit 3 = `D0`, bit 2 = `D1`, bit 1 = `P`, bit 0 = `Q` **(orden propuesto)**. Un 1 significa "en el último frame que recibí, ese canal tuvo ticks bloqueados o ruidosos". El emisor lo muestra en su LOG.

---

## 9. Colas

Cada equipo tiene sus propias colas. Existen porque cada sentido solo puede llevar un frame a la vez.

```
  mensajes escritos       frames listos para enviar          en los canales
 ┌──────────────┐      ┌───────────────────────────┐       ┌─────────────┐
 │ outbox (FIFO)│ ---> │ 0  ACK / NACK             │ ----> │ transmisor  │ ---> otro equipo
 └──────────────┘      │ 1  retransmisión          │       │ un frame    │
                       │ 2  START / DATA / END     │       └──────┬──────┘
                       │ 3  PING / PONG            │              │ enviado
                       └───────────────────────────┘              v
                                    ^                  ┌──────────────────────┐
                                    └── NACK/timeout ──│ waiting: un frame    │
                                                       │ bloqueado hasta ACK  │ ---> ACK: listo
                                                       └──────────────────────┘
```

| Cola | Qué guarda | Orden | Equivalente en CC7 |
|---|---|---|---|
| Outbox | mensajes escritos por el usuario | FIFO | cola de trabajos nuevos |
| Ready | frames listos para enviar | por prioridad; FIFO dentro del nivel | cola ready |
| Transmisor | el único frame que está en los canales | uno a la vez; no se interrumpe | proceso en ejecución |
| Waiting | frame enviado que espera su ACK | uno a la vez, con timeout | proceso bloqueado por I/O |
| Reparación | celdas buenas de un frame que falló | hasta que llega la repetición | buffer |
| Inbox | bytes recibidos y validados hasta el END | FIFO | buffer de entrega |

### Prioridades de la cola ready

| Nivel | Qué | Por qué |
|---|---|---|
| 0 | ACK / NACK | el otro equipo está detenido esperándolo |
| 1 | Retransmisión | ya va tarde |
| 2 | START / DATA / END del mensaje actual | trabajo normal |
| 3 | PING / PONG | solo cuando no hay nada más |

**Aging:** un frame que espera más de 3 turnos en ready sube un nivel. Nada espera para siempre. (1 turno = el tiempo de un frame.)

### Estados de un frame

```
  NEW --> READY --> RUNNING --> WAITING --> DONE
            ^                      │
            └── NACK o timeout ────┘      (después de 8 reintentos: FAILED)
```

| Estado | Significado | Pasa a | Cuándo |
|---|---|---|---|
| NEW | su mensaje está en el outbox | READY | el frame anterior del mensaje ya recibió su ACK |
| READY | espera turno | RUNNING | el transmisor queda libre y es el de mayor prioridad |
| RUNNING | sus 10 matrices salen por los canales | WAITING | termina la última matriz (ACK, NACK, PING y PONG pasan directo a DONE) |
| WAITING | espera su ACK | DONE | llega el ACK con su SEQ |
| WAITING | espera su ACK | READY nivel 1 | llega un NACK o vence el timeout |
| READY nivel 1 | retransmisión | FAILED | 8 reintentos sin ACK |

### Ejemplo: los dos equipos envían al mismo tiempo

A envía 'h', B envía 'k', y el profesor interfiere el DATA de A. `[n]` es el nivel de prioridad.

| Turno | Ready de A | A envía | Ready de B | B envía | Al final del turno |
|---|---|---|---|---|---|
| 1 | `[2]` START(h) | START(h) | vacía | nada | B recibe START y encola ACK. El usuario de B escribe 'k'. |
| 2 | vacía (START en waiting) | nada | `[0]` ACK, `[2]` START(k) | ACK | El ACK sale antes que el START propio. DATA(h) entra a ready. |
| 3 | `[2]` DATA(h) | DATA(h) | `[2]` START(k) | START(k) | Interferencia: B no resuelve la matriz 5, guarda las celdas buenas y encola NACK. A encola ACK. |
| 4 | `[0]` ACK | ACK | `[0]` NACK | NACK | DATA(h) pasa de waiting a ready nivel 1. DATA(k) entra a ready. |
| 5 | `[1]` DATA(h) retx | DATA(h) retx | `[2]` DATA(k) | DATA(k) | B llena los huecos y el CRC-8 pasa. Los dos encolan ACK. |
| 6 | `[0]` ACK | ACK | `[0]` ACK | ACK | Los dos DATA quedan en DONE. END entra a ready. |
| 7 | `[2]` END | END | `[2]` END | END | Ambos reciben END y encolan ACK. |
| 8 | `[0]` ACK | ACK | `[0]` ACK | ACK | Mensajes completos: A muestra 'k' y B muestra 'h'. |

---

## 10. El mensaje

Un mensaje de chat son varios frames, cada uno con su ACK.

| Frame | DATA | Cuántos |
|---|---|---|
| START | encoding: 0 = UTF-8, 1 = Extended ASCII (CP437), 2 = Extended ASCII (ISO-8859-1) | 1 |
| DATA | un byte del texto | uno por byte (UTF-8 usa de 1 a 4 bytes por carácter) |
| END | cantidad de bytes enviados mod 256 | 1 |

Ejemplos:

- 'h' en UTF-8: `START(0) DATA(68) END(1)`
- 'ñ' en UTF-8: `START(0) DATA(C3) DATA(B1) END(2)`
- 'ñ' en ISO-8859-1: `START(2) DATA(F1) END(1)`

Reglas:

1. El receptor muestra el mensaje como completo solo cuando llega END y su cantidad coincide con los bytes recibidos.
2. Si la cantidad no coincide, el mensaje se marca como incompleto.
3. Si llega un START con un mensaje abierto, el mensaje anterior se descarta como incompleto.
4. Un DATA o END fuera de un mensaje se reporta como error y se ignora.
5. Si un frame queda en FAILED, el emisor detiene el mensaje y lo marca como no entregado.

---

## 11. Vida del enlace

```
  SIN SEÑAL ──encender──> HELLO ──oigo un frame──> SOLO RECIBO ──PONG o ACK──> IDLE <───────┐
      ^                                                 ^                        │          │
      │                                                 │                mensaje │          │ END + ACK
      │                                 sin ACK ni PONG │                        v          │
      └──────────── no se oye nada ─────────────────────┴──────────────────── TRANSFER ─────┘
```

| Estado | Qué significa | Pasa a | Cuándo |
|---|---|---|---|
| SIN SEÑAL | no se ha oído ningún frame válido | HELLO | al encender, el equipo envía un PING de inmediato |
| HELLO | cada equipo anuncia su configuración con PING; el otro responde PONG | SOLO RECIBO | llega un frame válido |
| SOLO RECIBO | oigo al otro, pero nada confirma que mis frames le llegan | IDLE | llega un PONG o un ACK |
| IDLE | conectado y sin mensajes | TRANSFER | hay un mensaje en el outbox o llega un START |
| TRANSFER | un mensaje en curso | IDLE | END y su ACK |
| IDLE o TRANSFER | conectado | SOLO RECIBO | 7.5 tiempos de frame sin ACK ni PONG |
| cualquiera | | SIN SEÑAL | 7.5 tiempos de frame sin oír ningún frame válido |

- **PING:** se envía cuando el equipo lleva 3 tiempos de frame sin enviar nada. Cualquier frame recibido cuenta como señal de vida.
- **Configuración distinta:** si el CRC-8 anunciado por el otro equipo no coincide con el propio, se avisa al usuario y se le ofrece adoptar el del otro.
- En la interfaz: 🟢 conectado (IDLE o TRANSFER), 🟡 solo recibo, 🔴 sin señal.

---

## 12. Constantes

| Constante | Valor | Para qué |
|---|---|---|
| Canales por sentido | 5: CLK, D0, D1, P, Q | |
| Lecturas por tick | 4 | distinguir válido, bloqueado y ruidoso |
| Frecuencia | 1 Hz (configurable) | toda la evaluación es a 1 Hz |
| Ticks por matriz | 5 | 4 de datos + 1 de validación vertical |
| Matrices por frame | 10 | 40 bits |
| SYN | `1010 1010` | estabilizar el medio |
| SFD | `B3` | inicio del frame |
| SEQ | 0 a 15 | detectar frames repetidos |
| Timeout de ACK | 2 tiempos de frame | |
| Reintentos | 8 | después: FAILED |
| Aging | 3 turnos | |
| PING | tras 3 tiempos de frame sin enviar | |
| Ventana de vida | 7.5 tiempos de frame | |
| Capacidad de la matriz | 4 bits por 5 ticks = 0.8 × Hz bits/s | por sentido |
| Dato útil por frame | 8 bits por 50 ticks = 0.16 × Hz bits/s | por sentido, sin contar el ACK |

A 1 Hz: una matriz dura 5 s, un frame 50 s, y un frame con su ACK 100 s.

---

## 13. Resultados verificados

### Canales bloqueados y bits mentirosos

Fuerza bruta sobre los 16 medios bytes. Script: `experiments/matrix_nibble.py`.

| Caso | Recuperado | Se pide de nuevo | Dato incorrecto aceptado | Total |
|---|---|---|---|---|
| 1, 2 o 3 canales bloqueados toda la matriz | todos | 0 | 0 | 64 / 96 / 64 |
| 4 canales bloqueados | 0 | 16 | 0 | 16 |
| 1 vivo y pierde 1 tick | 320 | 0 | 0 | 320 |
| 1 vivo y pierde 2 ticks | 0 | 640 | 0 | 640 |
| 2 vivos y cada uno pierde 1 tick | 2400 | 0 | 0 | 2400 |
| 2 vivos y cada uno pierde 2 ticks | 8976 | 624 | 0 | 9600 |
| los 4 apagados 1, 2 o 3 ticks seguidos | todos | 0 | 0 | 80 / 64 / 48 |
| 1, 2 o 3 bits mentirosos, nada bloqueado | todos | 0 | 0 | 320 / 3040 / 18240 |
| 1 canal mintiendo de cualquier forma | 1984 | 0 | 0 | 1984 |
| 1 bloqueado + 1 canal mintiendo | 5952 | 0 | 0 | 5952 |
| 2 bloqueados + 1 canal mintiendo | 3072 | 2880 | 0 | 5952 |
| 2 canales mintiendo, ninguno bloqueado | 12000 | 80256 | 0 | 92256 |
| 3 bloqueados + el último mintiendo | 0 | 1024 | 960 | 1984 |

Distancia mínima entre matrices: 8.

**Punto débil:** con un solo canal vivo, lo único que lo valida es su propio bit vertical. Si ese canal miente con una columna que parece válida, la matriz acepta un dato incorrecto y solo el CRC-8 del frame lo detecta.

### Parpadeo rápido

Cada tick del canal interferido son 4 lecturas al azar; 2 de cada 16 veces parece un bit válido. 20000 matrices por caso. Script: `experiments/flicker_nibble.py`.

| Caso | Sin la regla de ruido: recuperado / incorrecto | Con la regla de ruido: recuperado / incorrecto |
|---|---|---|
| 2 parpadeando + 2 limpios | 93.6% / 0% | 100% / 0% |
| 3 parpadeando + 1 limpio | 80.6% / 2.9% | 100% / 0% |
| 2 parpadeando + 1 bloqueado + 1 limpio | 91.7% / 0.68% | 100% / 0% |
| 1 parpadeando + 2 bloqueados + 1 limpio | 99.9% / 0% | 100% / 0% |
| 4 parpadeando | 0.6% / 10.95% | 0% / 0.08% |

Lo que no se recupera se pide de nuevo. "Incorrecto" es lo que acepta la matriz; el CRC-8 todavía detecta 255 de cada 256.

### La misma lectura en los 4 canales

De las 32 lecturas posibles iguales en todos los canales: sin invertir `D1`, 1 es una matriz válida (la de puros ceros). Con `D1` invertido, ninguna lo es y la más cercana queda a 5 celdas.

---

## 14. Estado de implementación

| Parte | En el código hoy | Falta |
|---|---|---|
| Chat web, LOG, osciloscopio | sí | mostrar la matriz y sus validaciones |
| Presentación (UTF-8, Extended ASCII) | sí | |
| Mensaje START / DATA / END | sí | |
| Frame, CRC-8 ×4, SEQ | sí | |
| ACK / NACK, stop-and-wait, timeout, 8 reintentos, duplicados | sí | |
| Cola con prioridad | 2 niveles (control, datos) | 4 niveles, aging |
| Estados del enlace, PING / PONG, HELLO con CRC-8 | sí (conectado, solo recibo, sin señal) | |
| Line coding | v2: Manchester + paridad `P`, 3 canales + CLK | la matriz v6b con 5 canales |
| Tres tipos de lectura, `D1` invertido | no | todo |
| Buffer de reparación | no | todo |
| Reporte de canales en ACK / PONG | no | todo |
| PHY en la placa (GPIO) | 1 lectura por tick | 4 lecturas por tick |
| Medio simulado (laptop) | sí, con botones de tapar, IR y ruido | adaptarlo a 5 canales |

---

## 15. Puntos abiertos y optimizaciones pendientes

**Abiertos (hay que decidirlos al construir):**

1. Qué significa cada señal del `CLK` más allá de "tick" e "inicio de matriz": el silencio y el inicio de frame están solo propuestos ([sección 7](#7-frame)).
2. Si SYN y SFD viajan dentro de matrices (así está escrito aquí) o los reemplaza la marca del `CLK`.
3. El formato de una línea del LOG para la matriz: fila recibida, validaciones que pasaron, estado de las colas.
4. La regla exacta de reparación y el orden de los bits del reporte de canales ([sección 8](#8-enlace-ack-nack-y-retransmisión)).
5. Los medios físicos: con las piezas actuales alcanzan 3 canales por sentido y el diseño necesita 5.

**Optimizaciones de tiempo (dejadas para después a propósito):**

1. Que un ACK interrumpa un frame de datos entre dos matrices (espera de 5 s en vez de 50 s).
2. Repetir solo la matriz que falló en lugar del frame completo.
3. Sacar SYN y SFD de las matrices (frame de 30 s en vez de 50 s).
4. Volver a un byte por matriz (v6): la mitad del tiempo, pero solo sobreviven 2 canales bloqueados.

**Refuerzos pendientes:**

1. Memoria de canales: un canal que estuvo ruidoso sigue sin creerse durante las siguientes matrices. No probado.
2. Repartir los 4 canales de datos en al menos 3 medios, para que un solo tipo de interferencia no los alcance a todos.

---

## Anexo: las 16 matrices

Cada columna muestra los 5 bits del canal, del tick 0 al tick 4. "D1 en el canal" es `D1` ya invertido, como viaja.

| Hex | a b c d | D0 | D1 | D1 en el canal | P | Q |
|---|---|---|---|---|---|---|
| 0 | 0 0 0 0 | 0 0 0 0 0 | 0 0 0 0 0 | 1 1 1 1 1 | 0 0 0 0 0 | 0 0 0 0 0 |
| 1 | 0 0 0 1 | 0 0 0 1 1 | 0 0 1 0 1 | 1 1 0 1 0 | 0 0 1 1 0 | 0 1 1 1 1 |
| 2 | 0 0 1 0 | 0 0 1 0 1 | 0 1 0 0 1 | 1 0 1 1 0 | 0 1 1 0 0 | 1 1 1 1 0 |
| 3 | 0 0 1 1 | 0 0 1 1 0 | 0 1 1 0 0 | 1 0 0 1 1 | 0 1 0 1 0 | 1 0 0 0 1 |
| 4 | 0 1 0 0 | 0 1 0 0 1 | 1 0 0 1 0 | 0 1 1 0 1 | 1 1 0 1 1 | 1 1 1 0 1 |
| 5 | 0 1 0 1 | 0 1 0 1 0 | 1 0 1 1 1 | 0 1 0 0 0 | 1 1 1 0 1 | 1 0 0 1 0 |
| 6 | 0 1 1 0 | 0 1 1 0 0 | 1 1 0 1 1 | 0 0 1 0 0 | 1 0 1 1 1 | 0 0 0 1 1 |
| 7 | 0 1 1 1 | 0 1 1 1 1 | 1 1 1 1 0 | 0 0 0 0 1 | 1 0 0 0 1 | 0 1 1 0 0 |
| 8 | 1 0 0 0 | 1 0 0 0 1 | 0 0 0 1 1 | 1 1 1 0 0 | 1 0 0 1 0 | 1 0 1 1 1 |
| 9 | 1 0 0 1 | 1 0 0 1 0 | 0 0 1 1 0 | 1 1 0 0 1 | 1 0 1 0 0 | 1 1 0 0 0 |
| A | 1 0 1 0 | 1 0 1 0 0 | 0 1 0 1 0 | 1 0 1 0 1 | 1 1 1 1 0 | 0 1 0 0 1 |
| B | 1 0 1 1 | 1 0 1 1 1 | 0 1 1 1 1 | 1 0 0 0 0 | 1 1 0 0 0 | 0 0 1 1 0 |
| C | 1 1 0 0 | 1 1 0 0 0 | 1 0 0 0 1 | 0 1 1 1 0 | 0 1 0 0 1 | 0 1 0 1 0 |
| D | 1 1 0 1 | 1 1 0 1 1 | 1 0 1 0 0 | 0 1 0 1 1 | 0 1 1 1 1 | 0 0 1 0 1 |
| E | 1 1 1 0 | 1 1 1 0 1 | 1 1 0 0 0 | 0 0 1 1 1 | 0 0 1 0 1 | 1 0 1 0 0 |
| F | 1 1 1 1 | 1 1 1 1 0 | 1 1 1 0 1 | 0 0 0 1 0 | 0 0 0 1 1 | 1 1 0 1 1 |
