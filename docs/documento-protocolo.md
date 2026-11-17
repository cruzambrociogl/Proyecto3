# Protocolo PHY Chat — Documento del protocolo (v6b)

Rosangela Rodriguez (22000127) · Cruz Ambrocio (20005588) · Ciencias de la Computación VIII · noviembre de 2026

## 1. Resumen

El Protocolo PHY Chat lleva un chat de texto bidireccional entre dos placas BeagleBone Black por cinco canales físicos no convencionales, cada uno en un medio distinto: láser, infrarrojo, sonido, magnético y luz. Cada sentido tiene sus propios 5 canales: `CLK`, `D0`, `D1`, `P` y `Q`.

El protocolo no es serial ni completamente paralelo. La unidad básica es una **matriz de 5 ticks × 4 canales** que lleva medio byte:

- las **filas** son ticks que se envían uno tras otro: la parte serial;
- las **columnas** son canales que se envían al mismo tiempo: la parte paralela;
- cada canal de datos lleva los 4 bits con una mezcla XOR distinta, así que **basta con que sobreviva un canal** para recuperarlos;
- los bits se validan **durante** la transmisión, tick por tick, con tres familias de ecuaciones XOR: **horizontal** (entre canales), **diagonal** (entre ticks seguidos) y **vertical** (a lo largo de cada canal).

Sobre la matriz va el frame del enunciado (`SYN → SFD → CTRL → DATA → CRC`, más `SEQ`). El CRC-8 en cuatro variantes seleccionables, ACK/NACK, la retransmisión y las colas con prioridad quedan como la última red de seguridad, para lo que las ecuaciones no logran resolver.

Mecanismos principales:

- **Símbolo con tres tipos de lectura:** cada tick se lee 4 veces, así el receptor distingue un bit válido, un canal bloqueado (mano, puntero IR) y un canal ruidoso (parpadeo).
- **Recuperación por ecuaciones, no por votación:** la matriz sobrevive a 1, 2 o 3 canales bloqueados durante toda la matriz, y hasta 3 bits mentirosos, sin retransmitir.
- **Reparación entre retransmisiones:** el receptor guarda las celdas buenas de un frame que falló y las combina con la repetición.
- **Colas con prioridad y aging**, como en la planificación de procesos de un sistema operativo: primero ACK/NACK, luego retransmisiones, luego datos y al final las revisiones del enlace.
- **Reporte de canales:** cada ACK, NACK, PING y PONG le dice al emisor cuáles de sus canales llegaron dañados.

Toda la evaluación corre a **1 Hz** (configurable). El chat, el frame, el CRC-8, ACK/NACK y el enlace ya funcionan en una versión anterior del programa; la matriz que se describe aquí es el diseño que se está construyendo (sección 18). El primer canal real, láser hacia receptor infrarrojo, ya funciona en la placa a la velocidad que necesita el protocolo (15.6).

## 2. El problema

El enunciado pide una capa física de 3 a 8 líneas que lleve bytes de 8 bits sin ser un puerto paralelo convencional de 8 líneas. El diseño también cumple estas condiciones: debe ser un híbrido entre paralelo y serial, debe validar los bits durante la transmisión y no solo con el CRC al final del frame, la recuperación debe ser por ecuaciones (matrices), y debe seguir funcionando mientras se interfiere cualquier cantidad de canales de datos al mismo tiempo. El `CLK` nunca se interfiere.

## 3. Arquitectura

Cada placa corre **un solo programa** con las cuatro capas del enunciado como módulos separados. Las capas son una división lógica, no programas distintos.

```
  Placa A                                               Placa B
 ┌───────────────────────────────┐                   ┌───────────────────────────────┐
 │ Aplicación    chat web + LOG  │                   │ Aplicación    chat web + LOG  │
 │ Presentación  UTF-8/Ext.ASCII │                   │ Presentación  UTF-8/Ext.ASCII │
 │ Enlace        colas, ACK/NACK │                   │ Enlace        colas, ACK/NACK │
 │               SEQ, CRC-8      │                   │               SEQ, CRC-8      │
 │ Física        frame, matriz,  │  CLK D0 D1 P Q    │ Física        frame, matriz,  │
 │               símbolo         │ ────────────────> │               símbolo         │
 │               (GPIO)          │ <──────────────── │               (GPIO)          │
 └───────────────────────────────┘  CLK D0 D1 P Q    └───────────────────────────────┘
     navegador (HTTP)                                    navegador (HTTP)
```

| Capa | Unidad | Qué hace |
| --- | --- | --- |
| Aplicación | mensaje de texto | Web server: página del chat, LOG en vivo, vista de las matrices recibidas |
| Presentación | byte | Texto ↔ bytes en UTF-8 (1 a 4 bytes por carácter) o Extended ASCII (CP437, ISO-8859-1) |
| Mensaje | frames | `START`, un `DATA` por byte, `END` |
| Enlace | frame | Colas con prioridad, stop-and-wait, ACK/NACK, SEQ, CRC-8, estado del enlace |
| Frame | 40 bits | `SYN · SFD · CTRL · DATA · CRC · SEQ`, cortado en 10 medios bytes |
| Matriz | medio byte | 4 bits → 5 ticks × 4 canales, con validación horizontal, diagonal y vertical |
| Símbolo | tick | 4 lecturas por tick: válido, bloqueado o ruidoso |
| Medio | nivel | Cada canal termina como un 0/1 en un pin GPIO (15) |

El mismo programa también corre en una laptop con un medio simulado, donde unos botones bloquean, saturan o le meten ruido a cada canal. Así se prueba el protocolo antes de que existan los circuitos.

## 4. Unidades y canales

```
lectura < tick (4 lecturas) < matriz (5 ticks) < frame (10 matrices) < mensaje (bytes + 2 frames)
```

| Unidad | Contiene | Duración a 1 Hz |
| --- | --- | --- |
| Lectura | una muestra del sensor (0 o 1) | 0.25 s |
| Tick | 4 lecturas por canal = una fila de la matriz | 1 s |
| Matriz | 5 ticks × 4 canales = 20 celdas = 4 bits de datos | 5 s |
| Frame | 10 matrices = 40 bits | 50 s |
| Mensaje | START + un DATA por byte + END | (bytes + 2) frames |

| Canal | Función | Interferencia |
| --- | --- | --- |
| `CLK` | marca cada tick y el inicio de cada matriz | nunca se interfiere |
| `D0` | los 4 bits en orden | puede quedar bloqueado o ruidoso |
| `D1` | los 4 bits corridos un tick; viaja **invertido** | igual |
| `P` | `D0 ^ D1` en cada tick | igual |
| `Q` | una mezcla diagonal de `D0` y `P` | igual |

Los dos sentidos no comparten nada en el medio. En reposo todos los emisores están apagados (nivel 0) y el `CLK` está en silencio.

## 5. Símbolo y reloj

### 5.1 Tres tipos de lectura

Cada tick se divide en 4 cuartos. El emisor mantiene un nivel por cuarto y el receptor lee cada canal una vez, a la mitad de cada cuarto.

| 4 lecturas | Significado | Causa típica |
| --- | --- | --- |
| `0 0 1 1` | bit 1 | |
| `1 1 0 0` | bit 0 | |
| `0 0 0 0` | **bloqueado** | una mano entre el emisor y el sensor |
| `1 1 1 1` | **bloqueado** | un sensor saturado, un puntero IR |
| cualquier otro | **ruidoso** | parpadeo, ruido |

Un bit es una transición, como en la codificación Manchester, así que un canal pegado en un nivel nunca puede pasar por un dato. Las reglas:

1. Un tick bloqueado o ruidoso es una celda desconocida (`E`).
2. Si un canal mostró **ruido** en cualquier tick de una matriz, no se le cree durante toda esa matriz: todas sus celdas pasan a desconocidas, incluso las que se veían válidas. Un parpadeo rápido puede imitar por casualidad un patrón válido (2 veces de cada 16); esta regla elimina esas celdas falsas.
3. Un canal que solo estuvo **bloqueado** conserva sus ticks buenos.
4. **`D1` viaja invertido.** El emisor lo invierte y el receptor lo vuelve a invertir. Sin esto, la matriz de puros ceros es válida, y la misma interferencia en los cuatro sensores (todos a oscuras o todos iluminados) podría pasar como dato. Con `D1` invertido, ninguna lectura uniforme es una matriz válida (19.3).

### 5.2 El reloj

| Patrón del `CLK` | Significado |
| --- | --- |
| `1 1 0 0` | tick normal |
| `1 0 1 0` | tick 0: inicio de una matriz (doble parpadeo) |
| silencio | entre frames, o sin transmisión |

El receptor sigue el ritmo del `CLK` que recibe, no su propio reloj, así que cada sentido puede ir a su propia velocidad. Como el `CLK` nunca se interfiere, el primer tick después de un silencio es el tick 0 de la matriz 0 de un frame nuevo; SYN y SFD lo confirman cuando se pueden resolver.

## 6. La matriz

### 6.1 Recetas

Los 4 bits son `a b c d`, con `a` el más significativo. Cada celda tiene una receta fija:

```
            D0        D1       P        Q
  tick 0    a         b        a^b      a^b^c
  tick 1    b         c        b^c      b^c^d
  tick 2    c         d        c^d      a^b^c^d
  tick 3    d         a^b      a^b^d    a^c^d
  tick 4    a^b^c^d   a^c^d    b        a^b^d      <- validación vertical
```

Las columnas no se eligieron a mano. Son ventanas de una sola secuencia, `s[k+4] = s[k] ^ s[k+1]`, que empieza con `a, b, c, d` (una secuencia de registro de desplazamiento de longitud máxima, período 15):

```
s0=a  s1=b  s2=c  s3=d  s4=a^b  s5=b^c  s6=c^d  s7=a^b^d  s8=a^c  s9=b^d
s10=a^b^c  s11=b^c^d  s12=a^b^c^d  s13=a^c^d  s14=a^d
```

`D0` empieza en `s0`, `D1` en `s1`, `P` en `s4` y `Q` en `s10`. Cada columna son 4 términos seguidos más su XOR. **Cuatro términos seguidos de esta secuencia siempre determinan `a b c d`**, por eso basta con un solo canal que sobreviva. Los desplazamientos se eligieron probando todas las opciones y quedándose con la mayor distancia entre matrices válidas con 4, 3, 2 y 1 canales vivos.

### 6.2 Las tres validaciones

Todas son ecuaciones XOR que deben dar par.

| Validación | Regla | Cuándo |
| --- | --- | --- |
| Horizontal | `P[t] = D0[t] ^ D1[t]` | en cada tick, incluido el tick 4 |
| Diagonal | `D1[t] = D0[t+1]` y `Q[t] = D0[t] ^ P[t+1]`, para t = 0, 1, 2 | en cada tick desde el tick 1 |
| Vertical | celda del tick 4 = XOR de las 4 celdas de arriba del mismo canal | en el tick 4 |

Una falla horizontal señala el tick; una falla vertical señala el canal; su cruce es la celda equivocada. Es la misma idea de la paridad por filas y diagonales (row-diagonal parity) del almacenamiento RAID-6, aplicada a canales en vez de discos.

### 6.3 Ejemplo: 'h' = `0110 1000`

Un byte son dos matrices, primero la mitad alta.

```
  0110          D0  D1  P   Q          1000          D0  D1  P   Q
  tick 0        0   1   1   0          tick 0        1   0   1   1
  tick 1        1   1   0   0          tick 1        0   0   0   0
  tick 2        1   0   1   0          tick 2        0   0   0   1
  tick 3        0   1   1   1          tick 3        0   1   1   1
  tick 4        0   1   1   1          tick 4        1   1   0   1
```

Lo que viaja por los canales para `0110` (4 lecturas por tick, `D1` ya invertido):

| Canal | Tick 0 | Tick 1 | Tick 2 | Tick 3 | Tick 4 | Bits de la matriz |
| --- | --- | --- | --- | --- | --- | --- |
| `CLK` | `1 0 1 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | inicio de matriz en el tick 0 |
| `D0` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 0 1 1 0 0 |
| `D1` | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 1 1 0 1 1 (viaja como 0 0 1 0 0) |
| `P` | `0 0 1 1` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `0 0 1 1` | 1 0 1 1 1 |
| `Q` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | 0 0 0 1 1 |

Las 16 matrices están en el anexo.

## 7. Cómo decide el receptor

### 7.1 Regla de decisión

Al terminar el tick 4 el receptor tiene 20 celdas, cada una 0, 1 o desconocida.

1. **Marcar lo desconocido:** ticks bloqueados o ruidosos, y todas las celdas de un canal que mostró ruido.
2. **Resolver.** Cada celda conocida es una ecuación XOR en `a, b, c, d`; las celdas conocidas se comparan con las 16 matrices válidas.
   - Una sola coincide en todo: se acepta. Si había celdas desconocidas, quedó **reconstruida**.
   - Más de una coincide: no llegó suficiente información. La matriz queda **perdida**, y el receptor lo sabe.
   - Ninguna coincide: algún canal miente; sigue el paso 3.
3. **Corregir mentiras.**
   - *Pocos bits mentirosos:* se toma la matriz válida más cercana solo dentro del radio seguro. Con `gap` = la menor cantidad de celdas conocidas en que difieren dos matrices válidas, y `e` = las diferencias con la más cercana, se acepta si `2·e < gap` y es la única a esa distancia.
   - *Un canal completo mintiendo:* se descarta cada canal por turno; se acepta si lo que queda coincide con una sola matriz y en todas las pruebas que coinciden aparece la misma.
   - *Si no:* la matriz queda **detectada como mala** y se trata como perdida.
4. **Matriz perdida:** el frame no se puede completar. El receptor guarda las celdas buenas (sección 9, punto 5) y responde NACK.

El receptor nunca adivina. Una matriz o se resuelve con las ecuaciones o se declara perdida.

Con los 4 canales vivos, el tick 0 ya da `a, b, c` y el tick 1 da `d`: el medio byte se conoce en 2 ticks y el resto solo lo confirma. Con un solo canal vivo se conoce en 4 ticks. Más canales vivos significa conocer el dato antes; esa es la parte paralela trabajando.

### 7.2 Casos para la defensa

**A. Un bit mentiroso** (parpadeo en `D1`, tick 2: lee 1 en vez de 0)

```
            D0  D1  P   Q
  tick 0    0   1   1   0
  tick 1    1   1   0   0
  tick 2    1  [1]  1   0    falla horizontal: 1^1 = 0 pero P = 1      -> indica la fila
  tick 3    0   1   1   1    falla diagonal:   D1[2] = 1 pero D0[3] = 0
  tick 4    0   1   1   1    falla vertical de D1: 1^1^1^1 = 0 pero V = 1 -> indica la columna
```

El cruce de la fila y la columna es el mentiroso; se regresa a 0.

**B. Una mano sobre `D0`, `D1` y `P` durante toda la matriz** (solo `Q` vivo)

```
            D0  D1  P   Q
  tick 0    E   E   E   0     a^b^c   = 0
  tick 1    E   E   E   0     b^c^d   = 0
  tick 2    E   E   E   0     a^b^c^d = 0    con tick 0: d = 0; con tick 1: a = 0
  tick 3    E   E   E   1     a^c^d   = 1    c = 1; el tick 1 da b = 1
  tick 4    E   E   E   1     validación
```

Resultado `0 1 1 0`, correcto y sin retransmisión.

**C. El último canal también pierde un tick.** `Q` lee `0 E 0 1 1`. La celda perdida es el XOR de las otras cuatro: `0^0^1^1 = 0`. Después se resuelve como en B.

**D. El último canal pierde dos ticks.** `Q` lee `0 E E 1 1`. Quedan tres ecuaciones para 4 bits, y tanto `0110` como `0001` cumplen. El receptor guarda las 3 celdas buenas y responde NACK. Una celda buena más de la repetición decide (`Q` en el tick 1 es 0 para `0110` y 1 para `0001`). Este es el camino de la demostración: validación/CRC → NACK → retransmisión.

## 8. Frame

El frame del enunciado, sin cambios. La matriz solo es la forma en que viajan sus bits.

| Campo | Bits | Contenido |
| --- | --- | --- |
| SYN | 8 | `1010 1010`: deja que el medio y el receptor se estabilicen |
| SFD | 8 | `B3` = `1011 0011`: inicio del frame |
| CTRL | 4 | tipo de frame |
| DATA | 8 | un byte |
| CRC | 8 | CRC-8 sobre dos bytes: `(CTRL << 4) | SEQ` y `DATA` |
| SEQ | 4 | número de secuencia, 0 a 15 |

Los 40 bits van del más significativo al menos significativo, 4 bits por matriz:

```
  matriz   0    1    2    3    4     5    6    7    8    9
  campo    SYN  SYN  SFD  SFD  CTRL  DATA DATA CRC  CRC  SEQ
```

Ejemplo: un DATA con 'h' (`68`), SEQ 1 y CRC-8/SMBUS (`5D`) son los medios bytes `A A B 3 1 6 8 5 D 1`.

| CTRL | Nombre | Campo DATA |
| --- | --- | --- |
| 1 | DATA | un byte del texto |
| 2 | ACK | reporte de canales (bits 3 a 0) |
| 3 | NACK | reporte de canales (bits 3 a 0) |
| 4 | START | id de la codificación |
| 5 | END | bytes del mensaje mod 256 |
| 6 | PING | id de la variante de CRC-8 (bits 7 y 6) + reporte de canales (bits 3 a 0) |
| 7 | PONG | igual que PING |

**CRC-8 seleccionable:** SMBUS (id 0), AUTOSAR (1), SAE-J1850 (2), MAXIM-DOW (3). El CRC cubre CTRL y SEQ además de DATA, así que un tipo o un número de secuencia dañado también se detecta. PING y PONG siempre se revisan con SMBUS, para que dos placas con configuraciones distintas puedan leer el anuncio de la otra.

**Inicio del frame:** el `CLK` está en silencio entre frames; el primer tick después de un silencio es el tick 0 de la matriz 0. SYN y SFD viajan dentro de las matrices 0 a 3, como exige el enunciado, y confirman el inicio.

## 9. Enlace: ACK, NACK y retransmisión

1. **Stop-and-wait.** Cada frame START, DATA y END espera su ACK antes de que salga el siguiente.
2. **ACK.** Se envía con el mismo SEQ cuando el frame está completo y el CRC-8 pasa.
3. **NACK.** Se envía cuando una matriz quedó perdida o el CRC-8 falla.
4. **Timeout.** Si no llega ni ACK ni NACK en 2 tiempos de frame, el frame se repite (la otra placa puede estar a la mitad de su propio frame antes de poder responder).
5. **Reparación.** El receptor guarda las celdas buenas de un frame que falló. Cuando llega la repetición:
   - una matriz de la repetición que se resuelve sola se usa tal cual;
   - si no, se combinan las celdas conocidas de las dos copias y se vuelve a resolver; si las copias se contradicen en alguna celda, se descartan las celdas guardadas;
   - al final decide el CRC-8 del frame. Las celdas guardadas se borran cuando se acepta un frame.
6. **Reintentos.** Se repite el frame completo, como máximo 8 veces; después queda FAILED.
7. **Duplicados.** Si se pierde un ACK y llega una repetición con el mismo SEQ, el receptor la descarta y vuelve a enviar el ACK. START siempre abre un mensaje nuevo y nunca es duplicado.
8. **Reporte de canales.** ACK, NACK, PING y PONG llevan 4 bits: bit 3 = `D0`, bit 2 = `D1`, bit 1 = `P`, bit 0 = `Q`. Un 1 significa "en el último frame que recibí, ese canal tuvo ticks bloqueados o ruidosos". El emisor lo muestra en su LOG, así los dos lados ven qué canal está siendo atacado.

## 10. Colas

Cada sentido lleva un frame a la vez y un frame tarda 50 s a 1 Hz, así que las dos placas necesitan colas de espera. Siguen la planificación de procesos (CPU scheduling) de los sistemas operativos.

### 10.1 Las colas

```
  mensajes escritos       frames listos para enviar          en los canales
 ┌──────────────┐      ┌───────────────────────────┐       ┌─────────────┐
 │ outbox (FIFO)│ ---> │ 0  ACK / NACK             │ ----> │ transmisor  │ ---> otra placa
 └──────────────┘      │ 1  retransmisión          │       │ un frame    │
                       │ 2  START / DATA / END     │       └──────┬──────┘
                       │ 3  PING / PONG            │              │ enviado
                       └───────────────────────────┘              v
                                    ^                  ┌──────────────────────┐
                                    └── NACK/timeout ──│ waiting: un frame    │
                                                       │ bloqueado hasta ACK  │ ---> ACK: listo
                                                       └──────────────────────┘
```

| Cola | Qué guarda | Orden | Equivalente en sistemas operativos |
| --- | --- | --- | --- |
| Outbox | mensajes escritos por el usuario | FIFO | cola de trabajos nuevos |
| Ready | frames listos para enviar | por prioridad, FIFO dentro de cada nivel | cola ready |
| Transmisor | el frame que está en los canales | uno a la vez, sin interrupción | proceso en ejecución (running) |
| Waiting | frame enviado que espera su ACK | uno a la vez, con timeout | proceso bloqueado por I/O |
| Reparación | celdas buenas de un frame que falló | hasta que llega la repetición | buffer |
| Inbox | bytes recibidos y validados hasta el END | FIFO | buffer de entrega |

### 10.2 Prioridades y aging

| Nivel | Frames | Por qué |
| --- | --- | --- |
| 0 | ACK / NACK | la otra placa está detenida esperándolo |
| 1 | retransmisión | ya va atrasado |
| 2 | START / DATA / END | trabajo normal |
| 3 | PING / PONG | solo cuando no hay nada más |

**Aging (envejecimiento):** un frame que espera más de 3 turnos en la cola ready sube un nivel, así nada espera para siempre. Un turno es el tiempo de un frame.

### 10.3 Estados de un frame

```
  NEW --> READY --> RUNNING --> WAITING --> DONE
            ^                      │
            └── NACK o timeout ────┘      (después de 8 reintentos: FAILED)
```

| Estado | Significado | Pasa a | Cuándo |
| --- | --- | --- | --- |
| NEW | su mensaje está en el outbox | READY | el frame anterior del mensaje recibió su ACK |
| READY | espera su turno | RUNNING | el transmisor está libre y tiene la mayor prioridad |
| RUNNING | sus 10 matrices están en los canales | WAITING | termina la última matriz (ACK, NACK, PING y PONG pasan directo a DONE) |
| WAITING | espera su ACK | DONE | llega el ACK con su SEQ |
| WAITING | espera su ACK | READY, nivel 1 | llega un NACK o vence el timeout |
| READY, nivel 1 | retransmisión | FAILED | 8 reintentos sin ACK |

### 10.4 Ejemplo: las dos placas envían al mismo tiempo

A envía 'h', B envía 'k', y alguien interfiere el DATA de A. `[n]` es el nivel de prioridad.

| Turno | Ready de A | A envía | Ready de B | B envía | Al final del turno |
| --- | --- | --- | --- | --- | --- |
| 1 | `[2]` START(h) | START(h) | vacía | nada | B recibe START y encola ACK; el usuario de B escribe 'k' |
| 2 | vacía | nada | `[0]` ACK, `[2]` START(k) | ACK | El ACK sale antes que el START propio de B; DATA(h) entra a ready |
| 3 | `[2]` DATA(h) | DATA(h) | `[2]` START(k) | START(k) | Interferencia: B no puede resolver la matriz 5, guarda las celdas buenas y encola NACK; A encola ACK |
| 4 | `[0]` ACK | ACK | `[0]` NACK | NACK | DATA(h) regresa a ready, nivel 1; DATA(k) entra a ready |
| 5 | `[1]` DATA(h) retx | DATA(h) | `[2]` DATA(k) | DATA(k) | B llena los huecos y el CRC-8 pasa; los dos encolan ACK |
| 6 | `[0]` ACK | ACK | `[0]` ACK | ACK | Los dos DATA quedan DONE; END entra a ready |
| 7 | `[2]` END | END | `[2]` END | END | Los dos reciben END y encolan ACK |
| 8 | `[0]` ACK | ACK | `[0]` ACK | ACK | A muestra 'k' y B muestra 'h' |

## 11. Mensaje y presentación

Un mensaje del chat son varios frames, cada uno con su propio ACK.

| Frame | DATA | Cuántos |
| --- | --- | --- |
| START | codificación: 0 = UTF-8, 1 = Extended ASCII (CP437), 2 = Extended ASCII (ISO-8859-1) | 1 |
| DATA | un byte del texto | uno por byte (UTF-8 usa de 1 a 4 por carácter) |
| END | cantidad de bytes enviados mod 256 | 1 |

Ejemplos:

- 'h' en UTF-8: `START(0) DATA(68) END(1)`
- 'ñ' en UTF-8: `START(0) DATA(C3) DATA(B1) END(2)`
- 'ñ' en ISO-8859-1: `START(2) DATA(F1) END(1)`
- '😀' en UTF-8: `START(0) DATA(F0) DATA(9F) DATA(98) DATA(80) END(4)`

Reglas:

1. El mensaje se muestra completo solo cuando llega el END y su cuenta coincide con los bytes recibidos.
2. Si la cuenta no coincide, el mensaje se marca como incompleto.
3. Un START con un mensaje abierto descarta el anterior como incompleto.
4. Un DATA o END fuera de un mensaje se registra como error y se ignora.
5. Si un frame termina en FAILED, el emisor detiene el mensaje y lo marca como no entregado.

## 12. Vida del enlace

```
  SIN SEÑAL ──encender──> HELLO ──oigo un frame──> SOLO RECIBO ──PONG o ACK──> IDLE <───┐
      ^                                                 ^                        │      │
      │                                                 │                mensaje │      │ END+ACK
      │                                 sin ACK ni PONG │                        v      │
      └──────────── no se oye nada ─────────────────────┴──────────────────── TRANSFER ─┘
```

| Estado | Significado | Pasa a | Cuándo |
| --- | --- | --- | --- |
| SIN SEÑAL | no se ha oído ningún frame válido | HELLO | al encender, la placa envía un PING |
| HELLO | cada placa anuncia su configuración con PING; la otra responde PONG | SOLO RECIBO | llega un frame válido |
| SOLO RECIBO | oigo a la otra placa, pero nada confirma que mis frames le llegan | IDLE | llega un PONG o un ACK |
| IDLE | conectado, sin mensajes | TRANSFER | hay un mensaje en el outbox, o llega un START |
| TRANSFER | un mensaje en curso | IDLE | END y su ACK |
| IDLE o TRANSFER | conectado | SOLO RECIBO | 7.5 tiempos de frame sin ACK ni PONG |
| cualquiera | | SIN SEÑAL | 7.5 tiempos de frame sin un frame válido |

- Se envía un PING después de 3 tiempos de frame sin enviar nada. Cualquier frame recibido cuenta como señal de vida.
- Si la otra placa anuncia una variante de CRC-8 distinta, se avisa al usuario y se le ofrece adoptarla.
- En la página del chat: verde = conectado (IDLE o TRANSFER), amarillo = solo recibo, rojo = sin señal.

## 13. LOG

Cada placa lleva un LOG en vivo, que se muestra en la página del chat y se guarda en un archivo. La matriz corre a 1 Hz a propósito, para que una persona pueda seguirla. Cada entrada lleva la hora y el sentido (TX o RX).

| Evento | Qué registra |
| --- | --- |
| Tick | las 4 lecturas de cada canal y su clase: válido, bloqueado o ruidoso |
| Matriz | las 20 celdas, qué validaciones fallaron (horizontal, diagonal, vertical) y el resultado: ok, reconstruida, corregida, perdida |
| Frame | CTRL, SEQ, DATA, la variante de CRC-8, CRC correcto o fallido |
| ACK / NACK | enviado o recibido, su SEQ, el reporte de canales |
| Retransmisión | qué frame, número de reintento, causa (NACK o timeout), celdas guardadas y reparadas |
| Colas | cambios de estado del frame (NEW → … → DONE / FAILED), nivel de prioridad, aging |
| Enlace | cambios de estado (SIN SEÑAL, HELLO, SOLO RECIBO, IDLE, TRANSFER) y la configuración de la otra placa |
| Mensaje | START con su codificación, END con su cuenta, completo / incompleto / no entregado |

La página también dibuja cada matriz recibida como una cuadrícula de 5 × 4, marcando las celdas desconocidas, las validaciones que fallan y las celdas reconstruidas.

## 14. Constantes

| Constante | Valor | Para qué |
| --- | --- | --- |
| Canales por sentido | 5: `CLK`, `D0`, `D1`, `P`, `Q` | |
| Lecturas por tick | 4 | distinguir válido, bloqueado y ruidoso |
| Frecuencia | 1 Hz (configurable) | la velocidad de la evaluación |
| Ticks por matriz | 5 | 4 de datos + 1 de validación vertical |
| Matrices por frame | 10 | 40 bits |
| SYN | `1010 1010` | estabilizar |
| SFD | `B3` | inicio del frame |
| SEQ | 0 a 15 | detectar repeticiones |
| Timeout del ACK | 2 tiempos de frame | |
| Reintentos | 8 | después FAILED |
| Aging | 3 turnos | |
| PING | después de 3 tiempos de frame sin enviar | |
| Ventana de vida | 7.5 tiempos de frame | |
| Capacidad de la matriz | 4 bits por 5 ticks = 0.8 × Hz bit/s | por sentido |
| Datos útiles | 8 bits por 50 ticks = 0.16 × Hz bit/s | por sentido, sin contar el ACK |

A 1 Hz una matriz tarda 5 s, un frame 50 s y un frame con su ACK 100 s. El diseño ignora la velocidad a propósito; las variantes más rápidas están en la sección 20.

## 15. Implementación física

### 15.1 Placas

- Dos placas BeagleBone Black, un programa en cada una (Debian 10, Python 3.7, solo la biblioteca estándar).
- Los GPIO trabajan a **3.3 V y no toleran 5 V**. Toda salida de un sensor llega a la placa con 3.3 V como máximo, y ningún emisor se alimenta desde un pin GPIO.
- Mientras llega la segunda placa, los dos nodos corren en una sola BBB, cada uno con sus propios pines. Pasar a dos placas solo cambia el archivo de configuración de pines.
- La luz y el sonido no necesitan tierra común entre las dos placas.

### 15.2 Medios y canales

Cada uno de los 5 canales de un sentido usa un medio distinto.

| Canal | Medio | Emisor | Receptor | 0 / 1 | Estado |
| --- | --- | --- | --- | --- | --- |
| `CLK` | láser rojo, 650 nm | módulo KY-008 | fototransistor IR DL-591 + etapa de ganancia con NPN | haz apagado / encendido | construido y medido, un sentido (15.6) |
| `D0` | infrarrojo | LED IR de 5 mm | fototransistor IR DL-591 | apagado / encendido | planeado |
| `D1` | sonido | buzzer | módulo de micrófono KY-038 (comparador LM393, salida digital) | silencio / tono | planeado |
| `P` | magnético | electroimán (bobina) | sensor de efecto Hall, salida digital | sin campo / campo | planeado |
| `Q` | luz | por definir (provisional) | por definir | oscuro / iluminado | por definir |

**Por qué esta asignación:**

- El `CLK` va en el láser, el único canal ya medido y el que se estabiliza más rápido. El `CLK` nunca se interfiere.
- Los cuatro canales de datos usan cuatro medios distintos, dos de luz (`D0`, `Q`) y dos que no son luz (`D1`, `P`). Una mano o un puntero IR sobre la luz deja vivos el sonido y el magnetismo; un ruido cerca del micrófono deja vivos los otros tres. Un solo tipo de interferencia nunca alcanza a los cuatro, y basta con un canal (7.2, caso B).
- Aunque el láser, el infrarrojo y la luz cuenten como un solo medio (la tabla del enunciado pone "luz / infrarrojo" en una sola fila), luz, sonido y magnetismo son tres medios distintos.

**Pendiente:** las piezas que ya se tienen cubren los canales de láser, infrarrojo y sonido en los dos sentidos (2 láseres, 2 LED IR, 4 receptores IR, 2 buzzers, 2 micrófonos). Faltan comprar los sensores Hall, las bobinas y los diodos, y elegir el quinto medio.

### 15.3 Reglas de los circuitos

- Solo 3.3 V hacia la BBB: cada receptor se alimenta del 3.3 V de la placa (P9_3) o pasa por un divisor.
- Cada emisor se conmuta con un transistor NPN desde su propia fuente; el pin GPIO solo maneja la base a través de una resistencia.
- La tierra de la placa y la de la fuente de los emisores están unidas.
- Un diodo en paralelo con cada bobina (el electroimán), para que el pico al apagarla nunca llegue al transistor.
- Cada receptor de luz va dentro de un tubo oscuro que deja entrar el haz y deja fuera la luz del cuarto.
- Sonido en los dos sentidos a la vez: cada micrófono apunta al buzzer de la otra placa y está aislado del buzzer de su propia placa (espuma o un tubo), con la sensibilidad baja.
- A 1 Hz cada medio debe seguir un cambio cada 250 ms (un cuarto de tick).

### 15.4 Conexiones de cada medio

**Emisor láser (construido).** El KY-008 trabaja a 5 V; el transistor mantiene los 5 V lejos de la placa.

```
  BBB P8_7 ──[1 kΩ]──── base     NPN
                        colector ───── KY-008 (−)
  fuente 5 V ─────────────────────────── KY-008 (S)
                        emisor ─────── GND  (unida a la GND de la BBB, P9_1)
```

**Receptor de luz (construido).** El DL-591 solo da unos 3 µA con el láser rojo (0.3 V sobre 100 kΩ), muy lejos de los 2 V que la placa necesita para leer un 1. Un segundo NPN multiplica esa corriente unas 100 a 200 veces.

```
  P9_3 (3.3 V) ──┬──────────── DL-591 pata corta
                 │             DL-591 pata larga─┬── base, NPN
              [10 kΩ]                            │
                 │                        [470 kΩ]  (funciona de 220 kΩ a 1 MΩ)
                 ├──── P8_17 (entrada)           │
                 │                               │
           colector, NPN                         │
           emisor ───────────── P9_1 (GND) ──────┘
```

La salida está **invertida**: haz encendido → 0 en el pin, haz apagado → 1. El programa deshace esto por pin, en la configuración de pines, antes de que la capa de símbolo vea las lecturas. La resistencia de la base a tierra drena las pequeñas corrientes de fuga; sin ella, el parpadeo de la luz del cuarto convirtió 7 de 28 lecturas de "apagado" en "encendido".

**Emisor infrarrojo (planeado).** El mismo driver que el láser, con el LED y su resistencia en serie desde la fuente de 5 V hasta el colector (unos 180 Ω para unos 20 mA). El receptor es el mismo circuito que el receptor de luz.

**Sonido (planeado).** El buzzer se conmuta con un NPN desde 5 V, como los otros emisores. Un buzzer activo solo necesita encendido/apagado; uno pasivo necesita que la placa genere el tono, lo que cambia el driver (falta revisarlo en las piezas). El KY-038 se alimenta con 3.3 V para que su salida digital sea segura para la placa; su potenciómetro fija el umbral. Su salida puede pulsar con el tono en vez de mantener un nivel, así que puede necesitar una etapa que lo sostenga (un filtro RC) para que se lea como un 1 estable durante un cuarto de tick. El transmisor de sonido usa P8_13, un pin con PWM por hardware, por si el buzzer resulta ser pasivo (15.5).

**Magnético (planeado).** El emisor es una bobina conmutada con un NPN (o un MOSFET pequeño) desde 5 V, con un diodo en paralelo con la bobina. El receptor es un sensor digital de efecto Hall. Uno común, el A3144, necesita al menos 4.5 V, así que se alimenta con 5 V, pero su salida es de colector abierto: se sube a **3.3 V** con una resistencia de 10 kΩ, nunca a 5 V, así el pin solo ve 3.3 V. La salida del sensor queda en bajo cuando hay campo (invertida, como el receptor de luz).

```
  Emisor (placa A)                               Receptor (placa B)

  5 V ──┬─────────┐                              5 V ─────────── Hall VCC
        │       diodo (cátodo a 5 V)             GND ─────────── Hall GND
     bobina       │                              P9_3 (3.3 V) ──[10 kΩ]──┬── Hall OUT
        ├─────────┘                                                      └── P8_16 (entrada)
        │
     colector
  P8_9 ──[1 kΩ]── base   NPN
     emisor ── GND
```

**Luz (provisional).** El quinto medio todavía no está elegido. Conserva los pines de `Q` del mapa de abajo, y su circuito sigue las mismas reglas: emisor a través de un transistor, salida del receptor con 3.3 V como máximo.

### 15.5 GPIO

- Cada pin se pone en modo GPIO antes de usarlo: las salidas como `gpio`, las entradas como `gpio_pd` (con pull-down, así una entrada suelta lee 0, como un canal bloqueado). El modo se pierde al reiniciar, así que el programa lo configura cada vez que abre un pin. En el modo por defecto, el valor del pin cambiaba en software pero no en el header.
- Los pines se manejan con la interfaz GPIO de Linux (sysfs).
- **Transmisor:** cada canal mantiene un nivel por cuarto de tick (4 por tick); el `CLK` marca el tiempo.
- **Receptor:** 4 lecturas por canal por tick, una a la mitad de cada cuarto, medidas desde el flanco del `CLK` recibido.

**Mapa de pines: solo el header P8, igual en las dos placas.** Cada placa necesita 5 salidas y 5 entradas. El header P8 tiene 46 pines, pero P8_3–P8_6 y P8_20–P8_25 son de la memoria interna (eMMC), P8_27–P8_46 de la salida HDMI y la configuración de arranque, y P8_1–P8_2 son tierra. Quedan 14 pines GPIO libres (P8_7 a P8_19 y P8_26), suficientes para los 10 necesarios y 4 de reserva.

| Canal | Medio | Salida (TX) | Entrada (RX) |
| --- | --- | --- | --- |
| `CLK` | láser | P8_7 | P8_17 |
| `D0` | infrarrojo | P8_8 | P8_18 |
| `D1` | sonido | P8_13 (PWM por hardware) | P8_15 |
| `P` | magnético | P8_9 | P8_16 |
| `Q` | luz | P8_10 | P8_26 |
| reserva | | P8_11, P8_12, P8_14, P8_19 (PWM por hardware) | |

- La salida de un canal en la placa A apunta a la entrada del mismo canal en la placa B, y al revés, así las dos placas usan la misma configuración de pines.
- P8 no tiene pines de alimentación. La alimentación sale de P9: 3.3 V en P9_3 / P9_4 (receptores y resistencias pull-up), 5 V en P9_7 / P9_8 o una fuente externa de 5 V (emisores), tierra en P9_1 / P9_2 o P8_1 / P8_2.
- P8_7 y P8_17 son los pines del canal láser ya construido y medido.
- Mientras no esté la segunda placa, los dos nodos corren en una sola: el nodo A usa este mapa en P8 y el nodo B usa pines libres de P9.

### 15.6 Medido en el hardware

Láser → DL-591 con la etapa de ganancia, una sola BBB, un programa de prueba que hace parpadear el láser y lee el receptor a la mitad de cada medio período.

| Prueba | Resultado |
| --- | --- |
| 1 Hz durante un minuto | todas las lecturas correctas (invertidas) |
| 2 Hz durante unos 85 s: un cambio cada 250 ms, leído 125 ms después (el cuarto de tick de 1 Hz) | todas las lecturas correctas |
| 4 Hz: lectura 62 ms después de cada cambio | cerca de la mitad de las lecturas mostró el nivel anterior: el receptor se estabiliza en 60 a 125 ms. Suficiente para 1 Hz, con poco margen más allá |
| Haz bloqueado | el receptor lee "oscuro" haga lo que haga el láser: el caso bloqueado |
| Sin la resistencia de la base a tierra | 7 de 28 lecturas de "apagado" salieron "encendido" |
| Luz del cuarto | ráfagas cortas de "encendido" falso cada unos 4 s; con la punta del tubo tapada, una corrida completa salió limpia. Para la demostración: un tubo más largo, apuntado lejos de pantallas y lámparas |

Una mano deja pasar luz entre los dedos; una tarjeta o un libro bloquean el haz por completo.

## 16. Demostración: errores físicos intencionales

El enunciado pide una prueba de error totalmente física que muestre CRC → NACK → retransmisión. Cada acción de abajo se hace a mano sobre los canales reales mientras el chat corre; el LOG muestra cada paso (13).

| Acción | Qué lee el receptor | Qué hace el protocolo |
| --- | --- | --- |
| Tarjeta sobre un canal | el mismo nivel en las 4 lecturas: bloqueado | se reconstruye con los otros canales, sin retransmitir |
| Mano o tarjeta sobre toda la luz (`D0`, `Q`) | dos canales de datos bloqueados | se reconstruye con sonido y magnetismo (`D1`, `P`) |
| Luz tapada y un sonido cerca del micrófono | solo `P` (magnético) limpio | se reconstruye con un solo canal (caso B) |
| Puntero IR sobre un receptor | saturado, `1 1 1 1`: bloqueado | se reconstruye, igual que con la tarjeta |
| Parpadeo rápido (dedos moviéndose frente a un haz) | patrones no válidos: ruidoso | no se le cree al canal durante toda la matriz; se reconstruye si queda un canal limpio |
| Bloquear los cuatro canales de datos durante una matriz completa (5 s a 1 Hz) | solo celdas bloqueadas | matriz perdida → NACK → retransmisión; las celdas guardadas de la copia fallida ayudan a la repetición (9, punto 5) |
| Dejar un canal y quitarle dos de sus ticks | 3 celdas buenas | matriz perdida → NACK; una celda más de la repetición decide (caso D) |
| Bloquear tres canales y perturbar el último | una columna que puede parecer válida | la matriz puede aceptarla; el CRC-8 del frame falla → NACK → retransmisión |

La última fila es el camino CRC → NACK → retransmisión del enunciado; las dos anteriores son el mismo camino, pero iniciado por la validación de la matriz. Bloquear los cuatro canales de datos hasta 3 ticks seguidos todavía se reconstruye (19.1), así que los bloqueos tienen que ser largos para provocar un NACK.

## 17. Decisiones de diseño

| Decisión | Alternativas consideradas | Por qué |
| --- | --- | --- |
| Matriz: filas seriales, columnas paralelas | Repartir un flujo de bits entre los canales; una frecuencia por canal; símbolos por cantidad de parpadeos | Las otras son seriales disfrazadas o amarran todos los canales a una misma ventana. En la matriz cada canal es independiente y completo |
| Medio byte por matriz | Un byte por matriz de 5 × 4 (el doble de rápido) | Un byte por matriz solo sobrevive a 2 canales bloqueados; medio byte sobrevive hasta que queda un canal |
| Ecuaciones XOR para recuperar | Votación por mayoría; solo retransmisión | La votación necesita que la mayoría de canales esté sana y no puede ubicar al mentiroso. Las ecuaciones reconstruyen el dato desde cualquier canal y señalan la celda equivocada |
| Columnas de una sola secuencia de registro de desplazamiento | Columnas de paridad hechas a mano | Cuatro términos seguidos determinan el medio byte, y los desplazamientos dan la mayor distancia entre matrices |
| 4 lecturas por tick | 1 lectura por tick | Con 1 lectura, un canal bloqueado parece un 0 o un 1 válido. Con 4, lo bloqueado y lo ruidoso se ven y se descartan |
| Canal ruidoso descartado durante toda la matriz | Creerle a los ticks que se ven válidos | El parpadeo imita ticks válidos por casualidad; con esta regla ningún caso de parpadeo aceptó datos equivocados mientras hubo un canal limpio (19.2) |
| `D1` invertido | Todos los canales con la misma polaridad | Elimina la única lectura uniforme que era una matriz válida |
| SYN y SFD dentro de las matrices | Que la marca del `CLK` los reemplace | El enunciado exige la estructura `SYN → SFD → CTRL → DATA → CRC`; quitarlos queda como opción de velocidad |
| Inicio del frame por el silencio del `CLK` | Buscar el SYN en los datos | El `CLK` nunca se interfiere, así que su silencio es un separador confiable aunque los canales de datos estén bloqueados |
| Stop-and-wait | Ventana deslizante | Un frame por sentido a la vez y 50 s por frame; una ventana agregaría estado sin ganar tiempo a 1 Hz |
| Repetir el frame completo, con reparación | Repetir solo la matriz que falló | Más simple y mantiene intacto el frame del enunciado; las celdas guardadas ya hacen que la repetición cuente. Repetir por matriz es una opción de velocidad |
| Cuatro niveles de prioridad con aging | Una sola cola FIFO | Un ACK no debe esperar detrás de frames de datos de 50 segundos, y el aging evita la inanición (starvation) |
| CRC sobre CTRL, SEQ y DATA | CRC solo sobre DATA | Si no, un tipo o un número de secuencia dañado pasaría sin notarse |

## 18. Estado de la implementación

| Parte | Estado |
| --- | --- |
| Chat web, LOG, vista de las señales | funcionando (versión anterior) |
| UTF-8 y Extended ASCII; START / DATA / END | funcionando |
| Frame, CRC-8 × 4, SEQ, ACK/NACK, stop-and-wait, timeout, reintentos, duplicados | funcionando |
| PING/PONG y estados del enlace | funcionando |
| Medio simulado con botones de interferencia | funcionando |
| Primer canal real (láser → receptor IR en la BBB) | funcionando; correcto a 1 y 2 Hz (15.6) |
| Canales infrarrojo, sonido y magnético; el quinto medio | planeado |
| Matriz, tres tipos de lectura, `D1` invertido, marca de matriz en el `CLK` | diseño, en construcción |
| Cuatro niveles de prioridad, aging, reparación, reporte de canales | diseño, en construcción |
| 4 lecturas por tick en los GPIO | diseño |

## 19. Resultados verificados

El diseño se revisó por fuerza bruta en todos los casos, con los scripts de `docs/experiments/`. Son resultados del diseño; las mediciones en el hardware están en 15.6.

### 19.1 Canales bloqueados y bits mentirosos

Los 16 medios bytes en todas las combinaciones. Script: `matrix_nibble.py`.

| Caso | Recuperados | Se piden de nuevo | Datos equivocados aceptados | Total |
| --- | --- | --- | --- | --- |
| 1, 2 o 3 canales bloqueados durante toda la matriz | todos | 0 | 0 | 64 / 96 / 64 |
| 4 canales bloqueados | 0 | 16 | 0 | 16 |
| 1 vivo y pierde 1 tick | 320 | 0 | 0 | 320 |
| 1 vivo y pierde 2 ticks | 0 | 640 | 0 | 640 |
| 2 vivos y cada uno pierde 1 tick | 2400 | 0 | 0 | 2400 |
| 2 vivos y cada uno pierde 2 ticks | 8976 | 624 | 0 | 9600 |
| los 4 a oscuras durante 1, 2 o 3 ticks seguidos | todos | 0 | 0 | 80 / 64 / 48 |
| 1, 2 o 3 bits mentirosos, nada bloqueado | todos | 0 | 0 | 320 / 3040 / 18240 |
| 1 canal mintiendo de cualquier forma | 1984 | 0 | 0 | 1984 |
| 1 bloqueado + 1 canal mintiendo | 5952 | 0 | 0 | 5952 |
| 2 bloqueados + 1 canal mintiendo | 3072 | 2880 | 0 | 5952 |
| 2 canales mintiendo, ninguno bloqueado | 12000 | 80256 | 0 | 92256 |
| 3 bloqueados + el último mintiendo | 0 | 1024 | 960 | 1984 |

Distancia mínima entre dos matrices válidas: 8 celdas.

### 19.2 Parpadeo rápido

Cada tick de un canal interferido son 4 lecturas al azar (2 veces de cada 16 parece un bit válido). 20,000 matrices por caso. Script: `flicker_nibble.py`.

| Caso | Sin la regla de ruido: recuperados / equivocados | Con la regla de ruido: recuperados / equivocados |
| --- | --- | --- |
| 2 parpadeando + 2 limpios | 93.6% / 0% | 100% / 0% |
| 3 parpadeando + 1 limpio | 80.6% / 2.9% | 100% / 0% |
| 2 parpadeando + 1 bloqueado + 1 limpio | 91.7% / 0.68% | 100% / 0% |
| 1 parpadeando + 2 bloqueados + 1 limpio | 99.9% / 0% | 100% / 0% |
| 4 parpadeando | 0.6% / 10.95% | 0% / 0.08% |

Lo que no se recupera se pide de nuevo. "Equivocados" es lo que la matriz acepta; el CRC-8 del frame todavía rechaza 255 de cada 256 de esos.

### 19.3 La misma lectura en todos los canales

De las 32 lecturas que son iguales en todos los canales, sin invertir `D1` una es una matriz válida (la de puros ceros). Con `D1` invertido ninguna lo es, y la matriz válida más cercana está a 5 celdas.

## 20. Límites y trabajo pendiente

- **Punto débil:** con tres canales bloqueados, la única revisión del último es su propio bit vertical. Si ese canal miente con una columna que parece válida, la matriz acepta datos equivocados (960 de 1984 casos en 19.1) y solo el CRC-8 del frame lo detecta.
- **Opciones de velocidad, dejadas para después a propósito:** dejar que un ACK pase entre dos matrices de un frame de datos (5 s en vez de 50 s); repetir solo la matriz que falló; sacar SYN y SFD de las matrices (frames de 30 s en vez de 50 s); volver a un byte por matriz (la mitad del tiempo, pero solo sobreviven 2 canales bloqueados).
- **Refuerzo:** recordar un canal que estuvo ruidoso y seguir sin creerle en las matrices siguientes (todavía sin probar).
- **Medios físicos:** faltan construir los canales infrarrojo, sonido y magnético, elegir el quinto medio (luz) y comprar los sensores Hall y las bobinas (15.2).

## 21. Referencias

**Estándares y especificaciones**

- F. Yergeau, "UTF-8, a transformation format of ISO 10646", [RFC 3629](https://www.rfc-editor.org/rfc/rfc3629), noviembre de 2003.
- ISO/IEC 8859-1:1998, *8-bit single-byte coded graphic character sets — Part 1: Latin alphabet No. 1*.
- IBM, *Code page 437* (el juego de caracteres original de la PC).
- IEEE Std 802.3, cláusula 7: codificación Manchester de la capa física de Ethernet a 10 Mb/s.
- *System Management Bus (SMBus) Specification*, versión 3, SBS Implementers Forum: revisión de errores de paquete con CRC-8.
- AUTOSAR, *Specification of CRC Routines* (Classic Platform).
- SAE J1850, *Class B Data Communications Network Interface*.
- Maxim Integrated, Application Note 27, "Understanding and Using Cyclic Redundancy Checks with Maxim 1-Wire and iButton Products".

**Publicaciones y libros**

- R. W. Hamming, "Error detecting and error correcting codes", *Bell System Technical Journal* 29(2), 147–160, 1950.
- S. W. Golomb, *Shift Register Sequences*, Holden-Day, 1967.
- P. Corbett, B. English, A. Goel, T. Grcanac, S. Kleiman, J. Leong, S. Sankar, "Row-Diagonal Parity for Double Disk Failure Correction", *USENIX FAST*, 2004.
- H. P. Anvin, ["The mathematics of RAID-6"](https://www.kernel.org/pub/linux/kernel/people/hpa/raid6.pdf), kernel.org.
- R. N. Williams, "A Painless Guide to CRC Error Detection Algorithms", 1993.
- G. Ewing, ["Catalogue of parametrised CRC algorithms"](https://reveng.sourceforge.io/crc-catalogue/).
- A. S. Tanenbaum, D. J. Wetherall, *Computer Networks*, 5.ª ed., Pearson, 2011 (capa física, entramado, stop-and-wait).
- J. F. Kurose, K. W. Ross, *Computer Networking: A Top-Down Approach*, 8.ª ed., Pearson, 2021 (transferencia confiable de datos).
- A. Silberschatz, P. B. Galvin, G. Gagne, *Operating System Concepts*, 10.ª ed., Wiley, 2018 (planificación por prioridad y aging).

## Anexo: las 16 matrices

Cada columna muestra los 5 bits del canal, del tick 0 al tick 4. "D1 en el canal" es `D1` ya invertido, como viaja.

| Hex | a b c d | D0 | D1 | D1 en el canal | P | Q |
| --- | --- | --- | --- | --- | --- | --- |
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
