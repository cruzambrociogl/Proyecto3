# PHY Chat — Capa Física No Convencional

Chat bidireccional entre dos equipos sobre canales físicos con reloj. Python 3 (solo stdlib), corre igual en la laptop y en la BeagleBone.

```
App (web chat + LOG)  ->  Presentación (UTF-8 1–4 bytes / Extended ASCII)
                      ->  Enlace (CRC-8, ACK/NACK, stop-and-wait, SEQ)
                      ->  Física (Frame SYN|SFD|CTRL|DATA|CRC|SEQ en N lanes por tick)
                      ->  Line coding: fec (Manchester + paridad P) | plain (nivel)
                      ->  PHY simulado (UDP)  |  PHY GPIO (BeagleBone)
```

Historia del diseño, feedback del profesor, decisiones y experimentos: [../docs/design-log.md](../docs/design-log.md). Especificación del protocolo aceptado (v6b, aún no construido): [../docs/protocol.md](../docs/protocol.md). Toda la documentación de contexto vive en `PROJECT03/docs/`; esta carpeta solo tiene la implementación.

## Line coding: sobrevivir a un canal interferido

Diseño completo, con tablas de verdad y casos: [../docs/diseno_canales.xlsx](../docs/diseno_canales.xlsx). Código: `phychat/linecode.py`.

Canales por dirección: **CLK + D0 + D1 + P**.

1. **Símbolo:** 4 muestras por tick. Bit 1 = `0011`, bit 0 = `1100` (transición a mitad de tick), CLK = `1100`. Otro patrón = canal borrado (E): un sensor tapado (`0000`) o saturado con IR (`1111`) ya no parece un dato válido.
2. **Paridad:** P = D0 ⊕ D1. Si un canal es E, vale el XOR de los otros dos: se reconstruye sin retransmitir.
3. **Historial:** un canal borrado en los últimos 8 ticks es sospechoso; si la paridad falla sin borrados, se invierte ese canal.
4. **CRC-8 + ACK/NACK** verifica la trama ya corregida. Con dos canales caídos a la vez falla → NACK → retransmisión.

Si CLK se pierde, los flancos a mitad de tick de los canales de datos dan el timing. `--coding plain` usa el esquema anterior (nivel por canal) para comparar.

## Frame

| Campo | Bits | Contenido |
|---|---|---|
| SYN | 4 ticks | todos los lanes alternan 1,0,1,0 (el medio se estabiliza) |
| SFD | 8 | `0xB3` = 1011 0011 |
| Control | 4 | 1 DATA, 2 ACK, 3 NACK, 4 START (DATA = encoding), 5 END (DATA = longitud mod 256), 6 PING, 7 PONG |
| DATA | 8 | 1 byte |
| CRC | 8 | CRC-8 sobre `[CTRL<<4 \| SEQ, DATA]`: SMBUS, AUTOSAR, SAE-J1850, MAXIM-DOW |
| [SEQ] | 4 | número de secuencia mod 16 (descarta duplicados si se pierde un ACK) |

En cada tick del canal CLK, el lane *j* lleva el bit *i·lanes + j*. Con CLK + 2 lanes un Frame son 20 ticks.

## Estado del enlace

- **Heartbeat:** sin tráfico, cada nodo manda PING cada ~1 s (o 3 Frames si el reloj es lento); el peer responde PONG. Indicador en la UI: 🟢 Conectado (lo oigo y me responde), 🟡 Solo recibo (lo oigo pero no confirma mis Frames: falla mi TX o su RX), 🔴 Sin señal.
- **Hello:** PING/PONG llevan en DATA el CRC-8 del emisor (`id << 6`) y siempre se verifican con CRC-8/SMBUS fijo, así cada nodo lee la configuración del otro aunque sea distinta. Si no coincide, la UI avisa y ofrece adoptar la del peer. Al cambiar el CRC se anuncia de inmediato.
- **Frecuencia:** el receptor no necesita conocerla, sigue los flancos de CLK. Además mide el reloj del peer (mediana del intervalo entre flancos) y con eso ajusta el timeout de ACK y el corte por reloj detenido, así ambos lados pueden usar `--hz` distinto.

## Correr en la laptop (medio simulado)

```
./run_sim.sh                 # A -> http://localhost:8081   B -> http://localhost:8082
./run_sim.sh --lanes 4 --hz 30
```

Panel de canales (lo que **recibe** ese nodo; cada botón se mantiene hasta volver a pulsarlo):

- **✋ Tapar:** mano entre emisor y sensor, el sensor ve todo 0.
- **🔦 IR:** puntero IR al sensor, todo 1.
- **〰 Ruido:** muestras al azar.

El punto de cada canal muestra su estado: verde OK, amarillo intermitente, rojo caído. El LOG marca en cada frame cuántos ticks se reconstruyeron. El slider **Ruido** invierte muestras al azar en todos los canales.

**🔬 Osciloscopio** (casilla en la cabecera): dibuja el último frame DATA recibido, tick por tick y canal por canal.

- Gris: lo emitido. Azul: lo recibido.
- Puntos: las 4 lecturas. Línea punteada: mitad del tick.
- Debajo de cada tick: lo que leyó el receptor (`1`, `0`, `E`, `E→1` reconstruido).
- Abajo: los bits que pasan al deframer.
- El botón 🔬 de cada RX en el LOG abre ese frame.

Conviene probarlo enviando un solo carácter.

Demos:

- **Un canal (cualquiera, incluido CLK) tapado:** el mensaje llega sin retransmisiones.
- **Dos canales tapados (p. ej. D0 + D1):** CRC/timeout → NACK → retransmisión.
- **Comparar:** `./run_sim.sh --coding plain` y tapar D1: el mensaje falla.

Tests: `python3 -m unittest -v tests.test_stack tests.test_fec`

## BeagleBone: loopback con cables (los dos nodos en una sola placa)

Puentes en el header P8:

| A.TX → B.RX | B.TX → A.RX |
|---|---|
| CLK P8_7 → P8_10 | CLK P8_14 → P8_17 |
| D0 P8_8 → P8_11 | D0 P8_15 → P8_18 |
| D1 P8_9 → P8_12 | D1 P8_16 → P8_26 |

```
scp -r phy-chat debian@192.168.7.2:~/
ssh debian@192.168.7.2
cd phy-chat
python3 tools/gpio_selftest.py config/bbb_loopback.json   # verifica cada cable
./run_bbb_loopback.sh                                     # luego abrir 192.168.7.2:8081 y :8082
```

El PHY GPIO todavía usa `--coding plain`: FEC necesita que el receptor muestree 4 veces por tick.

**GPIO de la BeagleBone = 3.3 V, NO tolera 5 V.** Salidas del Arduino o de módulos a 5 V necesitan divisor resistivo (p. ej. 10 kΩ / 20 kΩ) o level shifter.

## Analizador lógico

GND → P8_1. CH0 P8_7 (A CLK), CH1 P8_8 (A D0), CH2 P8_9 (A D1), CH3 P8_14 (B CLK), CH4 P8_15, CH5 P8_16. Muestreo 1 MHz, trigger flanco de subida en CH0. En Logic 2 el analizador *Simple Parallel* (clock CH0, datos CH1–CH2) muestra el valor de cada tick.

## Siguiente: medios reales

El código no cambia: entre el pin TX y el pin RX se reemplaza el cable por actuador → medio → sensor → comparador. Para medios lentos: bajar `--hz` y usar `--sample-delay-ms`.
