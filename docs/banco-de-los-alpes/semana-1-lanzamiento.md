# Banco de los Alpes — Semana 1: Lanzamiento del proyecto

> **Estado del documento:** borrador para decisión del equipo · v0.1 · 2026-10-09
>
> **Regla de este documento:** todo lo marcado como **🟡 DECISIÓN PENDIENTE** es una propuesta, no una decisión. Cada una trae opciones, una recomendación argumentada y el impacto de elegir otra cosa. La decisión final la toma el responsable del equipo y, cuando quede tomada, se cambia la marca a **✅ DECIDIDO (fecha, quién)** y, si es de arquitectura, se registra como ADR.

---

## Índice

0. [Registro de decisiones pendientes](#0-registro-de-decisiones-pendientes)
1. [Acta de Inicio](#1-acta-de-inicio)
2. [Reglas de Funcionamiento](#2-reglas-de-funcionamiento)
3. [Análisis de los seis módulos: ¿qué se extrae primero?](#3-análisis-de-los-seis-módulos-qué-se-extrae-primero)
4. [SAD 1: Introducción y alcance](#4-sad-1--introducción-y-alcance)
5. [SAD 2: Requisitos y atributos de calidad](#5-sad-2--requisitos-y-atributos-de-calidad)
6. [Rúbrica de Atributos de Calidad](#6-rúbrica-de-atributos-de-calidad--banco-de-los-alpes)
7. [Dudas para el tutor](#7-dudas-para-el-tutor)
8. [Checklist del entregable de la semana 1](#8-checklist-del-entregable-de-la-semana-1)

---

## 0. Registro de decisiones pendientes

| ID | Decisión | Opción recomendada | Alternativas | Dónde impacta | Estado |
|---|---|---|---|---|---|
| D-01 | Módulo(s) que se extraen primero | **A: Simulación + Scoring y decisión** | B: solo Simulación · C: Simulación + Clientes (lectura) | Alcance, SAD 1, ADR-001 | 🟡 Pendiente |
| D-02 | Líder del equipo | Integrante con rol de Integración | Cualquiera de los tres | Acta | 🟡 Pendiente |
| D-03 | Asignación de los tres roles | Ver §1.2 | — | Acta | 🟡 Pendiente |
| D-04 | Canal principal de comunicación | Microsoft Teams (cuenta Uniandes) | WhatsApp · Slack · Discord | Reglas | 🟡 Pendiente |
| D-05 | Frecuencia de sincronización | 2 síncronas/semana + daily asíncrona | 1 síncrona/semana · daily síncrona | Reglas | 🟡 Pendiente |
| D-06 | Mecanismo de decisión de arquitectura | Propuesta en ADR + consenso, desempate por el líder del área | Mayoría simple · líder decide | Reglas | 🟡 Pendiente |
| D-07 | Modelo de ramas | **GitHub Flow** (trunk + ramas cortas) | GitFlow · trunk-based puro | Git | 🟡 Pendiente |
| D-08 | Política de PR | 1 revisor obligatorio + CI verde | 2 revisores · 1 revisor del otro microservicio | Git | 🟡 Pendiente |
| D-09 | Convención de commits | **Conventional Commits** | Formato libre con ID de issue | Git | 🟡 Pendiente |
| D-10 | Prioridades de los atributos de calidad | Propuesta 1 (§6.2) | Propuesta 2 (§6.2) | Rúbrica, SAD 2 | 🟡 Pendiente |
| D-11 | Metas numéricas de los escenarios | Valores de §6.3 | Ajustar tras respuesta del tutor sobre volumen | Rúbrica | 🟡 Pendiente |
| D-12 | Alcance inicial del agente de IA | Solo lectura sobre Simulación; pre-scoring sin efecto vinculante | Sin acceso en el MVP · lectura de Scoring con consentimiento | Seguridad, ADR | 🟡 Pendiente |

---

## 1. Acta de Inicio

### 1.1 Datos generales

| Campo | Valor |
|---|---|
| Curso | Diseño y Construcción de APIs (MISO, Universidad de los Andes) |
| Equipo / Grupo | `Grupo{NN}` |
| Tutor asignado | `<nombre del tutor>` |
| Fecha de la reunión de lanzamiento | `AAAA-MM-DD` |
| Grabación de la reunión | `<enlace>`: publicar en la wiki, sección **"Seguimiento del proyecto"** |
| Repositorios | Base (monolito + fachada) · `F1_Grupo{NN}` · `F2_Grupo{NN}` |

### 1.2 Integrantes y roles

Los tres roles los define el enunciado y **no rotan** durante las ocho semanas.

| Integrante | Correo @uniandes.edu.co | Usuario GitHub | Rol en el proyecto | ¿Líder del equipo? |
|---|---|---|---|---|
| `<Integrante 1>` | | | Líder del microservicio de **Simulación** (repo F1) | |
| `<Integrante 2>` | | | Líder del microservicio de **Scoring** (repo F2) | |
| `<Integrante 3>` | | | **Integración**: fachada compartida y consolidación del SAD | 🟡 (propuesto, D-02) |

**🟡 D-02 · Líder del equipo.** La propuesta es que lo sea quien tiene el rol de Integración, porque ese rol ya ve el sistema completo (fachada, monolito, ambos servicios y el SAD) y es el punto natural de coordinación. La alternativa es separar el liderazgo de la integración para repartir mejor la carga. *Decide el equipo.*

**Responsabilidades del líder:** convocar y moderar las reuniones, llevar el acta y el seguimiento en la wiki, ser el canal con el tutor y desempatar cuando no haya consenso.

### 1.3 Horario de trabajo

| Actividad | Día | Hora | Duración | Modalidad |
|---|---|---|---|---|
| Sincronización 1 (planeación de la semana) | `<lunes>` | `<hh:mm>` | 45 min | Virtual |
| Sincronización 2 (revisión e integración) | `<jueves>` | `<hh:mm>` | 45 min | Virtual |
| Daily asíncrona | Lunes a viernes | antes de las 10:00 | — | Canal principal |
| Reunión con tutor | `<según agenda del tutor>` | | | |

Disponibilidad individual:

| Integrante | Franjas disponibles | Franjas no disponibles |
|---|---|---|
| `<Integrante 1>` | | |
| `<Integrante 2>` | | |
| `<Integrante 3>` | | |

### 1.4 Caso y propósito

Banco de los Alpes es una entidad financiera colombiana ficticia, vigilada por la Superintendencia Financiera de Colombia (SFC). El equipo se encarga de modernizar su **sistema de originación y gestión de crédito de consumo**, un monolito de más de ocho años sobre una base de datos compartida. Usa el patrón **Strangler Fig** para extraer funcionalidades hacia APIs detrás de una fachada estable, sin reescribir desde cero y manteniendo el monolito como fuente de verdad de todo lo que aún no se ha migrado.

### 1.5 Alcance del proyecto

> 🟡 **D-01 pendiente.** Abajo se redacta con la opción recomendada (A). Si se elige B o C, se ajusta con la tabla de §3.4.

**Qué se moderniza primero:**

- **Simulación** (F1): cálculo de cuota y monto máximo, expuesto como API versionada detrás de la fachada. Es lo primero y lo más frecuente que ve el cliente en la app, hoy lo puede tumbar un incidente de mora y casi no escribe estado. Es el tramo con mejor relación valor/riesgo para empezar el estrangulamiento.
- **Scoring y decisión** (F2): evaluación de una solicitud con el motor de reglas (APROBADO / NEGADO / REVISIÓN_MANUAL). Es el dolor de despliegue explícito del caso: el equipo de reglas no puede publicar un modelo sin una ventana coordinada con pagos. Además es el punto de entrada natural del agente de IA de pre-scoring.
- **Fachada strangler** compartida, con enrutamiento por porcentaje, reversión al monolito y trazabilidad de qué lado atendió cada petición.

**Qué queda fuera de alcance:**

- **Desembolso** y **Ciclo de vida** (pagos, refinanciación, mora): tocan el flujo de pagos, así que aplica PCI-DSS 4.0 completo y mueven dinero real. Siguen en el monolito.
- **Solicitudes** como sistema de registro: sigue siendo autoritativo en el monolito. Scoring lee la solicitud y publica su decisión, pero no se vuelve dueño del ciclo de vida de la solicitud.
- **Clientes** como sistema de registro: el dato maestro sigue en el monolito y los servicios nuevos lo consultan.
- Integración real con burós de crédito, canales de producción, migración masiva de datos históricos, y certificación formal ante la SFC (se diseña para que sea certificable, pero no se certifica).

### 1.6 Objetivos del equipo

1. **Extraer** Simulación y Scoring del monolito detrás de una fachada strangler, con contrato OpenAPI versionado antes de escribir implementación (*contract-first*), sin interrumpir la originación.
2. **Garantizar reversibilidad y trazabilidad**: devolver el 100 % del tráfico al monolito en minutos sin perder datos, y poder demostrar para cada solicitud qué lado la resolvió y por qué.
3. **Sustentar con evidencia medida** los seis atributos de calidad: la rúbrica llega a la semana 8 con medida real en todos.
4. **Diseñar para los cinco consumidores**, incluido el agente de IA, con un alcance de acceso explícito, mínimo y defendible.
5. **Documentar cada decisión relevante como ADR** y consolidarlas en un SAD único y coherente para el comité.

### 1.7 Restricciones del caso

| # | Restricción | Consecuencia en el diseño |
|---|---|---|
| R1 | Entidad **vigilada por la SFC** | Trazabilidad completa e ininterrumpida del historial crediticio, sin "zonas ciegas" entre monolito y servicio nuevo. Auditoría de accesos. |
| R2 | **Mandato de finanzas abiertas**: Decreto 0368 de 2026 (reemplaza al 1297 de 2022) y Circular Externa 004 de 2024 de la SFC | APIs **versionadas y estables** hacia terceros autorizados, con estándares de interoperabilidad, seguridad y protección de datos. Los agregadores leen, pero **no inician desembolsos**. |
| R3 | **No reescribir desde cero** (decisión no negociable) | Strangler Fig: extracción incremental, coexistencia y monolito como fuente de verdad de lo no migrado. |
| R4 | **PCI-DSS 4.0** sobre cualquier módulo que toque pagos | Razón principal para dejar Desembolso y Ciclo de vida fuera de la primera ola. |
| R5 | Carga con **picos de 5× a 8×** (campañas, quincenas) | La parte nueva debe aguantar el pico o devolver tráfico al monolito sin que el cliente lo note. |

### 1.8 Reglas de funcionamiento

Ver la [sección 2](#2-reglas-de-funcionamiento).

### 1.9 Dudas sobre el enunciado

Ver la [sección 7](#7-dudas-para-el-tutor). Se registran aquí y se envían al tutor antes de `<fecha>`.

---

## 2. Reglas de Funcionamiento

### 2.1 Comunicación

- **🟡 D-04 · Canal principal:** propuesta **Microsoft Teams** (canal del grupo con la cuenta Uniandes), que conserva el historial y permite grabar las reuniones. Alternativas: WhatsApp (más inmediato, pero el historial se pierde y no sirve como evidencia), Slack o Discord. Las decisiones técnicas **no** se toman en el chat: se llevan a un issue, un PR o un ADR.
- **🟡 D-05 · Frecuencia de sincronización:** propuesta de **dos reuniones síncronas por semana** (planeación y revisión/integración) más una **daily asíncrona** en el canal con el formato *hice / haré / bloqueos*. La alternativa es una sola síncrona semanal, que deja menos margen para detectar bloqueos antes del cierre de cada entrega.

### 2.2 Toma de decisiones

**🟡 D-06 · Cómo se decide una decisión de arquitectura.** Propuesta:

1. Quien propone abre un **ADR en estado "Propuesto"** (contexto, opciones consideradas, decisión, consecuencias y cómo se revierte) en un PR.
2. Los otros dos integrantes tienen **48 horas** para comentar.
3. Se busca **consenso**. Si no se logra, decide el líder del área afectada (Simulación, Scoring o Integración). Si la decisión cruza áreas, decide el líder del equipo.
4. Al aprobarse, el ADR pasa a **"Aceptado"**. Si una decisión posterior lo reemplaza, se marca **"Reemplazado por ADR-NNN"** y nunca se borra.

**Toda decisión relevante se registra como ADR** en `docs/adr/NNN-titulo.md`, con la plantilla de Michael Nygard o MADR (a elegir).

### 2.3 Flujo de trabajo en Git

- **🟡 D-07 · Convención de ramas.** Propuesta: **GitHub Flow**, con `main` siempre desplegable y ramas cortas `tipo/issue-descripcion`, por ejemplo `feat/12-contrato-simulacion`, `fix/31-bola-scoring`, `docs/5-rubrica-v0.1` o `adr/3-politica-versionado`. Es simple para un equipo de tres y encaja con CI y despliegue continuo. GitFlow añade ramas `develop` y `release` que el proyecto no necesita.
- **🟡 D-08 · Política de Pull Requests.** Propuesta:
  - mínimo **1 revisor** que no sea el autor;
  - **CI en verde** (pruebas, lint y el *gate* de breaking changes del contrato cuando exista);
  - `main` protegida, sin push directo;
  - *squash merge*;
  - un PR no vive más de **3 días hábiles** sin revisión.

  Alternativa: dos revisores, más seguro pero lento con tres personas.
- **🟡 D-09 · Convención de mensajes de commit.** Propuesta: **Conventional Commits**, con el formato `tipo(alcance): descripción`. Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`. Ejemplo: `feat(simulacion): expone POST /v1/simulaciones`. Permite generar changelogs y ayuda a la evolutividad del contrato, porque `feat!` o un pie `BREAKING CHANGE:` marcan cambios incompatibles.

### 2.4 Definición de "Hecho" (Definition of Done)

Una historia o tarea está **hecha** cuando:

- [ ] El código tiene pruebas que pasan en CI.
- [ ] El contrato OpenAPI está actualizado y validado (lint) si el cambio toca la API.
- [ ] Pasó la revisión de PR según §2.3 y está integrado en `main`.
- [ ] La documentación está actualizada en la wiki (y en el SAD si cambia la arquitectura).
- [ ] La decisión quedó registrada como ADR cuando aplica.
- [ ] Si afecta un atributo de calidad, la rúbrica está actualizada (medida real o escenario).

### 2.5 Reparto de responsabilidades

> 🟡 Depende de D-03.

| Área | Responsable | Apoyo |
|---|---|---|
| Microservicio de Simulación (F1): contrato, implementación, pruebas, rendimiento | `<Integrante 1>` | `<Integrante 3>` |
| Microservicio de Scoring (F2): contrato, motor de reglas, seguridad (BOLA, scopes) | `<Integrante 2>` | `<Integrante 3>` |
| Fachada strangler: enrutamiento, canary, *rollback*, trazabilidad | `<Integrante 3>` | `<Integrante 1>`, `<Integrante 2>` |
| SAD consolidado y Rúbrica de Atributos de Calidad | `<Integrante 3>` | Todos |
| Registro de ADR (custodia del índice) | Líder del equipo | Todos proponen |
| CI/CD y *gate* de breaking changes | `<a definir>` | |
| Pruebas de carga (k6) | `<Integrante 1>` | |
| Modelado de amenazas (STRIDE) y alcance del agente de IA | `<Integrante 2>` | |
| Acta, seguimiento en la wiki y comunicación con el tutor | Líder del equipo | |

### 2.6 Compromisos de calidad

1. **Contract-first:** ningún endpoint se implementa sin su contrato OpenAPI revisado en un PR.
2. **Nada entra a `main` con CI en rojo** ni sin revisión.
3. **Cada atributo de calidad se sustenta con un número medido**, no con una impresión.
4. **Ningún cambio incompatible del contrato se publica sin nueva versión mayor** (lo verifica el *gate* de CI desde la semana 2).
5. **Toda petición que atraviesa la fachada lleva un identificador de correlación** y queda registrado qué lado (monolito o servicio nuevo) la atendió.

### 2.7 Reglas verificables (mínimo 5, con las cuatro categorías)

Criterio de evaluación: todas deben poder comprobarse objetivamente, y debe haber al menos una por categoría.

| # | Categoría | Regla | Cómo se verifica |
|---|---|---|---|
| RF-01 | Comunicación | Cada integrante publica su daily asíncrona (*hice / haré / bloqueos*) en el canal principal de lunes a viernes antes de las 10:00. | Historial del canal: % de días con daily por persona (meta ≥ 90 %). |
| RF-02 | Comunicación | Todo mensaje que pida una respuesta se contesta en menos de 24 horas en días hábiles. | Marca de tiempo de la pregunta y de la respuesta en el canal. |
| RF-03 | Puntualidad | Se asiste a las reuniones síncronas con un máximo de 5 minutos de retraso. Una ausencia se avisa con al menos 12 horas de anticipación. | Lista de asistencia en el acta de cada reunión. |
| RF-04 | Puntualidad | Los entregables semanales quedan en la wiki o en `main` **24 horas antes** de la fecha límite del curso. | Fecha del último commit o edición frente a la fecha límite. |
| RF-05 | Colaboración | Todo PR recibe una primera revisión en menos de 24 horas hábiles desde que se abre. | Historial de PR en GitHub (`created_at` frente a la primera revisión). |
| RF-06 | Colaboración | Cada integrante revisa al menos un PR de otro integrante por semana. | Lista de revisores en GitHub por semana. |
| RF-07 | Calidad del trabajo | Ningún PR se integra a `main` con CI fallido ni sin al menos 1 aprobación. | Reglas de protección de rama e historial de *merges*. |
| RF-08 | Calidad del trabajo | Toda decisión de arquitectura queda en un ADR enlazado desde el SAD, antes del cierre de la semana en que se tomó. | Índice de ADR frente a las decisiones listadas en el acta semanal. |

**Si se incumple una regla:** la primera vez, el líder lo menciona en la siguiente sincronización. Si se repite, queda registrado en el acta de seguimiento y se informa al tutor.

---

## 3. Análisis de los seis módulos: ¿qué se extrae primero?

> El caso pide decidir *"con criterio explícito, no con intuición"* y dejar por escrito las opciones descartadas. Este análisis es el insumo para **D-01** y para el futuro **ADR-001**.

### 3.1 Criterios

Cada criterio se califica de 1 a 5, donde **5 significa "más conviene extraerlo primero"**.

| Criterio | Qué pregunta | Atributo relacionado |
|---|---|---|
| C1 · Valor y visibilidad | ¿Cuánto tráfico o impacto de cliente tiene? ¿Cuánto mejora al aislarlo? | Rendimiento, escalabilidad |
| C2 · Aislamiento de fallos | ¿Hoy sufre por fallos de módulos ajenos? | Escalabilidad, disponibilidad |
| C3 · Independencia de despliegue | ¿Hay un dolor de despliegue acoplado que se resuelve al extraerlo? | Mantenibilidad |
| C4 · Bajo riesgo de consistencia | ¿Escribe poco estado compartido? (5 = casi solo lectura) | Consistencia |
| C5 · Bajo riesgo regulatorio | ¿Queda fuera de PCI-DSS y no mueve dinero? (5 = bajo riesgo) | Seguridad |
| C6 · Facilidad de reversión | ¿Se puede devolver el tráfico al monolito sin reconciliar datos? | Consistencia, evolutividad |
| C7 · Valor para open finance y consumidores | ¿Habilita consumidores externos, internos o el agente de IA? | Evolutividad |

### 3.2 Matriz

| Módulo | C1 | C2 | C3 | C4 | C5 | C6 | C7 | **Total /35** | Lectura |
|---|---|---|---|---|---|---|---|---|---|
| **Simulación** | 5 | 5 | 3 | 5 | 5 | 5 | 4 | **32** | Alto tráfico, casi sin estado, hoy lo tumba la mora y se revierte trivialmente. |
| **Scoring y decisión** | 4 | 3 | 5 | 3 | 4 | 3 | 5 | **27** | Es el dolor de despliegue explícito y el punto de entrada del agente de IA. Escribe la decisión, así que hay riesgo moderado de consistencia. |
| Clientes | 3 | 2 | 2 | 2 | 3 | 3 | 4 | 19 | Es el dato maestro del que dependen todos. Extraerlo primero rompe muchos acoplamientos a la vez. |
| Solicitudes | 4 | 2 | 2 | 1 | 4 | 1 | 3 | 17 | Es el corazón del estado. Partirlo primero crea la "zona ciega" que la SFC prohíbe. |
| Desembolso | 2 | 2 | 2 | 1 | 1 | 1 | 2 | 11 | Mueve dinero real, PCI-DSS completo y los agregadores no pueden iniciarlo. |
| Ciclo de vida | 2 | 1 | 4 | 1 | 1 | 1 | 2 | 12 | Pagos y mora (PCI). Es el que causa incidentes: conviene aislarlo de los demás, no tocarlo primero. |

> Las calificaciones son una **propuesta** para que el equipo las discuta. Si alguien no está de acuerdo con un número, se cambia aquí y queda el motivo.

### 3.3 Opciones para D-01

| Opción | Qué se extrae | A favor | En contra |
|---|---|---|---|
| **A (recomendada)** | **Simulación + Scoring** | Coincide con los dos repositorios F1 y F2 y con los roles del curso. Combina un tramo de bajo riesgo (Simulación) con uno que ataca el dolor de despliegue y el agente de IA (Scoring). Enseña los dos patrones clave: lectura sin estado y escritura con consistencia en el borde. | Scoring obliga a resolver pronto la consistencia de la decisión y la trazabilidad, que es el problema más difícil. |
| B | Solo Simulación | Riesgo mínimo y reversión trivial. | Deja sin atender el dolor de despliegue del motor de reglas y no ejercita la consistencia. Probablemente no cubre el alcance esperado en F2. |
| C | Simulación + Clientes (lectura) | Clientes de solo lectura habilita APIs de open finance para los agregadores. | Clientes es dato maestro muy acoplado. Su beneficio para el caso es menor que el de Scoring y no aprovecha el rol de líder de Scoring. |

**Recomendación: opción A.** Simulación primero: es la primera ola de tráfico y valida la fachada, el enrutamiento por porcentaje y la reversión con el menor riesgo. Scoring va en paralelo pero con un enrutamiento más conservador. La decisión que emite se registra con un identificador único reconciliable y el monolito sigue siendo el dueño de la solicitud. Así se evita la zona ciega que exige la SFC.

### 3.4 Respuesta a "la pregunta que abre el curso"

> *¿Cuál módulo, o cuáles, extraerían primero detrás de una fachada strangler, y por qué?*

**Borrador de respuesta, sujeto a D-01:**

Extraeríamos primero **Simulación** y, en paralelo con un despliegue más conservador, **Scoring y decisión**.

- **Simulación** es el módulo con mejor relación valor/riesgo. Es lo primero y lo más frecuente que ve el cliente en la app, hoy lo puede tumbar un incidente de mora con el que no tiene nada que ver, casi no escribe estado compartido y por eso se puede devolver al monolito en minutos sin reconciliar datos. Es el lugar ideal para probar la fachada, el enrutamiento por porcentaje, la observabilidad diferencial y el *rollback* antes de tocar algo más delicado.
- **Scoring** ataca el problema de mantenibilidad que más le duele al banco: el equipo de reglas no puede desplegar un modelo nuevo sin una ventana coordinada con pagos. También es donde va a vivir el agente de IA de pre-scoring, así que conviene diseñar su contrato y su modelo de autorización desde el principio. Su riesgo es la consistencia de la decisión. Lo mitigamos dejando la **solicitud** como propiedad del monolito: Scoring solo produce una decisión inmutable, trazable con un identificador de correlación y la versión del motor de reglas que la emitió.

**Descartamos por ahora:**

- **Desembolso y Ciclo de vida**: tocan pagos y PCI-DSS 4.0 completo, y mueven dinero real.
- **Solicitudes**: partir su estado al inicio crearía la zona ciega de trazabilidad que la SFC no admite.
- **Clientes**: es dato maestro del que dependen todos. Extraerlo primero rompe demasiados acoplamientos a la vez con poco beneficio inmediato.

---

## 4. SAD 1 — Introducción y Alcance

*Se completa en la semana 1.*

### 4.1 Problema de negocio

Banco de los Alpes origina y gestiona crédito de consumo con un **monolito de más de ocho años** sobre una base de datos compartida, donde los seis módulos (Clientes, Simulación, Solicitudes, Scoring y decisión, Desembolso, Ciclo de vida) se leen y escriben entre sí libremente. El sistema funciona y cumple la regulación, pero se volvió el cuello de botella de la entidad por tres razones:

1. **Acoplamiento de despliegue:** el motor de reglas de scoring no puede publicar un modelo nuevo sin una ventana de mantenimiento coordinada con pagos y refinanciación.
2. **Propagación de fallos:** un incidente en mora puede tumbar la simulación, que es la primera interacción del cliente en la app.
3. **Presión regulatoria:** el mandato de finanzas abiertas (Decreto 0368 de 2026 y CE 004 de 2024) exige exponer APIs versionadas y estables a terceros autorizados, con plazos que ya están corriendo. El monolito no puede dar esa estabilidad sin exponer su acoplamiento interno.

Una reescritura completa no llegaría a tiempo con la trazabilidad y el respaldo que exige la SFC. Una **extracción incremental (Strangler Fig)** sí, porque cada tramo extraído se puede certificar y exponer por separado.

### 4.2 Dominio

**Crédito de consumo de Banco de los Alpes:** originación (simulación, solicitud, scoring y decisión, desembolso) y gestión de las obligaciones ya desembolsadas (pagos, refinanciación, mora e historial).

**Consumidores del API:**

| # | Consumidor | Qué necesita | Qué no puede hacer |
|---|---|---|---|
| 1 | App móvil del banco | Baja latencia y disponibilidad en simulación y estado de solicitud | Ver datos de otro cliente |
| 2 | Agregadores fintech (open finance) | Contratos versionados y estables, con lectura de productos y saldos | **Iniciar desembolsos** |
| 3 | El propio monolito | Invocar y ser invocado sin fricción de integración durante la coexistencia | Saltarse la fachada en tramos ya migrados |
| 4 | Equipos internos (cobranza, contact center) | Seguir integrando sin esperar a que termine la migración | — |
| 5 | Agente de IA (asesoría / pre-scoring) | Lectura acotada para recomendar o pre-evaluar | 🟡 D-12: propuesta de **nunca** emitir decisiones vinculantes, desembolsar ni leer datos de clientes sin consentimiento explícito |

### 4.3 Restricciones del caso

- Entidad **vigilada por la Superintendencia Financiera de Colombia**, con trazabilidad completa e ininterrumpida del historial crediticio.
- **Mandato de finanzas abiertas** (Decreto 0368 de 2026 y Circular Externa 004 de 2024): APIs versionadas, estables, interoperables y seguras.
- **Decisión no negociable: no reescribir desde cero.** Se aplica Strangler Fig y el monolito es la fuente de verdad de lo no migrado.
- **PCI-DSS 4.0** completo sobre cualquier módulo que toque el flujo de pagos.

### 4.4 Alcance

> 🟡 Sujeto a **D-01** (recomendada: opción A).

**Qué parte del monolito se moderniza primero y por qué:**

- **Simulación**: es el módulo de mayor tráfico y visibilidad, casi sin estado compartido. Hoy se cae por fallos ajenos (mora) y se revierte sin reconciliar datos. Sirve para validar la fachada, el enrutamiento y el *rollback* con el menor riesgo.
- **Scoring y decisión**: resuelve el acoplamiento de despliegue del motor de reglas y prepara el punto de entrada controlado del agente de IA. La solicitud sigue siendo del monolito y la decisión se registra como un hecho inmutable y trazable.
- **Fachada strangler compartida**: punto único de entrada para los cinco consumidores, con versionado externo estable, enrutamiento por porcentaje, reversión en minutos y registro de qué lado atendió cada petición.

(Ver la matriz y las opciones descartadas en [§3](#3-análisis-de-los-seis-módulos-qué-se-extrae-primero).)

**Qué queda fuera de alcance:** Desembolso, Ciclo de vida (pagos, refinanciación, mora), Solicitudes y Clientes como sistemas de registro, integración real con burós y canales productivos, migración de datos históricos y certificación formal ante la SFC.

---

## 5. SAD 2 — Requisitos y Atributos de Calidad

*Se completa en la semana 1 y se refina en S4, S5 y S7.*

Esta sección expresa la Rúbrica de Atributos de Calidad como **escenarios de calidad de seis partes**: estímulo, fuente, artefacto, entorno, respuesta y medida. En la semana 1 las medidas son **metas**. Desde la semana 4 se reemplazan por **medidas reales** obtenidas de las pruebas.

### 5.1 Requisitos funcionales del alcance (borrador)

| ID | Requisito | Servicio |
|---|---|---|
| RF-SIM-01 | Calcular la cuota y el monto máximo a partir de monto, plazo, tasa e ingresos, sin crear una solicitud. | Simulación |
| RF-SIM-02 | Exponer la simulación como API versionada (`/v1/...`) para la app, los agregadores y el agente de IA. | Simulación |
| RF-SCO-01 | Evaluar una solicitud ENVIADA y producir APROBADO, NEGADO o REVISIÓN_MANUAL, con el detalle de las reglas aplicadas y la versión del motor. | Scoring |
| RF-SCO-02 | Consultar la decisión de una solicitud solo si el consumidor está autorizado sobre ese recurso. | Scoring |
| RF-FAC-01 | Enrutar cada petición al monolito o al servicio nuevo según un porcentaje configurable en caliente. | Fachada |
| RF-FAC-02 | Volver al 100 % monolito sin redespliegue. | Fachada |
| RF-FAC-03 | Registrar por petición el identificador de correlación, el lado que la atendió y el motivo del enrutamiento. | Fachada |

### 5.2 Escenarios de calidad

Ver la [Rúbrica de Atributos de Calidad](#6-rúbrica-de-atributos-de-calidad--banco-de-los-alpes) para la tabla completa y su versionamiento.

---

## 6. Rúbrica de Atributos de Calidad — Banco de los Alpes

> Página viva de la wiki. Se diligencia por primera vez en la semana 1 y se actualiza en las semanas 4, 5, 7 y 8. **No se reescribe desde cero:** la columna "Medida real" empieza vacía y se llena con evidencia. En la semana 8 debe tener medida real para los seis atributos.

**Equipo:** `Grupo{NN}` · **Versión:** v0.1 (semana 1) · **Última actualización:** `AAAA-MM-DD`, semana 1

### 6.1 Supuestos de carga

Están pendientes de confirmar con el tutor (ver la [duda T-03](#7-dudas-para-el-tutor)).

| Variable | Supuesto | Fuente |
|---|---|---|
| Solicitudes de crédito, operación normal | ~500 por hora | El caso dice "cientos por hora" |
| Pico (campaña o quincena) | 8× ⇒ ~4 000 solicitudes por hora | El caso dice "5 a 8 veces" y se toma el peor caso |
| Relación simulaciones / solicitud | ~10 simulaciones por solicitud creada | Supuesto: el cliente simula varias veces antes de solicitar |
| Simulaciones en pico | ~40 000 por hora ≈ **11 rps sostenidos**, con ráfagas de **50 rps** | Derivado |

### 6.2 Tabla resumen de prioridades

> **Regla de priorización honesta:** no todos pueden ser "alta". Hay dos propuestas para **🟡 D-10**.

**Propuesta 1 (recomendada): seguridad, consistencia y evolutividad altas.** El caso está gobernado por la regulación (SFC, open finance) y la estrategia strangler, así que lo que no se puede ceder es la protección de datos, la trazabilidad y la estabilidad del contrato. El rendimiento y la escalabilidad son importantes, pero existe una válvula de escape: devolver el tráfico al monolito.

| Atributo | Prioridad | Justificación | Semana en que se mide | Medida real |
|---|---|---|---|---|
| Rendimiento | **Media** | Simulación es lo primero que ve el cliente en la app y una latencia alta en campaña baja la conversión. Pero la carga absoluta es moderada y, si hay degradación, la fachada puede devolver tráfico al monolito. Se cede rendimiento máximo a cambio de controles de seguridad y trazabilidad en cada petición. | Semana 4 (k6) | |
| Seguridad | **Alta** | Es una entidad vigilada por la SFC y está sujeta a open finance (CE 004/2024). Una falla de autorización a nivel de objeto en Scoring expondría la información crediticia de un cliente a un tercero, incluido un agregador o el agente de IA. Eso es un incumplimiento regulatorio y una pérdida de confianza difícil de revertir. | Semana 5 (BOLA, STRIDE) | |
| Mantenibilidad | **Media** | Es la motivación de negocio de extraer Scoring: el equipo de reglas debe desplegar sin ventana coordinada con pagos. Se protege con estructura limpia y *fitness functions*, pero no se prioriza por encima de lo regulatorio. | Semanas 3 y 7 (fitness function, estructura) | |
| Escalabilidad | **Media** | Hay picos de 5× a 8× en campañas y quincenas, pero el volumen base es de cientos por hora. Un pico mal manejado en la parte nueva se puede devolver al monolito, así que se exige sostener el pico con un *error budget* explícito y no con escalamiento ilimitado. | Semana 7 (error budget bajo pico) | |
| Consistencia | **Alta** | La SFC exige trazabilidad completa e ininterrumpida del historial crediticio. Durante la coexistencia, una solicitud puede pasar por el monolito y por el servicio nuevo, y no puede quedar una zona ciega ni una decisión de scoring sin reconciliar. | Semana 7 (política de versión / canary) | |
| Evolutividad | **Alta** | El mandato de open finance exige APIs versionadas y estables para terceros autorizados. Los cinco consumidores no deben notar desde afuera que por dentro todo cambió. Un breaking change no controlado rompe a los agregadores y es un incumplimiento. | Semanas 2 y 7 (gate de breaking changes, claridad del contrato) | |

**Propuesta 2 (alternativa): seguridad, consistencia y rendimiento altos; evolutividad media.** Sirve si el equipo considera que la experiencia del cliente en la app (Simulación) es el criterio de éxito más visible para el comité. El costo es que la estabilidad del contrato queda menos protegida frente a open finance, que es justamente el reloj regulatorio del caso. **Por eso no se recomienda.**

### 6.3 Escenarios de calidad (uno por atributo)

Las medidas son **metas** en v0.1 (🟡 D-11).

#### Rendimiento

| Parte | Valor |
|---|---|
| **Estímulo** | Pico de peticiones de simulación de crédito. |
| **Fuente del estímulo** | Clientes en la app móvil durante una campaña comercial o una quincena de pago. |
| **Artefacto** | `POST /v1/simulaciones` del servicio de Simulación, a través de la fachada strangler. |
| **Entorno** | Pico de 8× el volumen normal (≈ 11 rps sostenidos, ráfagas de 50 rps) durante 15 minutos, con el 100 % del tráfico de simulación enrutado al servicio nuevo. |
| **Respuesta esperada** | El servicio calcula y devuelve cuota y monto máximo sin degradarse, y la fachada no añade latencia significativa. |
| **Medida de la respuesta** | **p95 < 300 ms** y **p99 < 800 ms** de extremo a extremo medidos en la fachada. **Tasa de error < 1 %**. Sobrecosto de la fachada **p95 < 20 ms**. Se mide con k6. |
| **Medida real** | *(semana 4)* |

#### Seguridad

| Parte | Valor |
|---|---|
| **Estímulo** | Una petición con un token válido intenta leer la decisión de scoring de una solicitud que pertenece a otro cliente (BOLA), o pide una acción fuera de su *scope*. |
| **Fuente del estímulo** | Un consumidor autenticado (app de otro cliente, agregador fintech o agente de IA) que manipula el identificador del recurso o el alcance solicitado. |
| **Artefacto** | `GET /v1/solicitudes/{id}/decision` del servicio de Scoring y la política de *scopes* de la fachada. |
| **Entorno** | Operación normal, con autenticación OAuth 2.0 / OIDC activa. |
| **Respuesta esperada** | Rechazo con **403** (o **404** para no revelar que el recurso existe, 🟡 a decidir en ADR), registro del intento en auditoría con el identificador de correlación, y ningún dato del recurso ajeno en la respuesta. El agente de IA y los agregadores no pueden invocar operaciones de escritura vinculantes. |
| **Medida de la respuesta** | **0 accesos indebidos** en la suite automatizada de BOLA. La prueba **falla si se retira el *guard*** de autorización. El 100 % de los intentos rechazados quedan en auditoría. Hay **0 amenazas STRIDE de severidad alta** sin mitigación. |
| **Medida real** | *(semana 5)* |

#### Mantenibilidad

| Parte | Valor |
|---|---|
| **Estímulo** | El equipo de riesgo pide cambiar una regla del motor de scoring, por ejemplo un nuevo umbral de capacidad de pago. |
| **Fuente del estímulo** | Equipo de negocio de riesgo de crédito. |
| **Artefacto** | Módulo de dominio (reglas) del servicio de Scoring. |
| **Entorno** | Tiempo de desarrollo, con el servicio en producción y tráfico parcial enrutado. |
| **Respuesta esperada** | El cambio se hace solo en la capa de dominio, sin tocar adaptadores ni el contrato. Se despliega de forma independiente, sin ventana coordinada con pagos ni redespliegue del monolito. |
| **Medida de la respuesta** | El cambio toca **≤ 2 archivos de la capa de dominio** y **0 de infraestructura o contrato**. Se despliega en **< 1 día** desde la aprobación. La *fitness function* de arquitectura (dependencias solo hacia adentro) pasa en CI en el **100 %** de los *builds*. |
| **Medida real** | *(semanas 3 y 7)* |

#### Escalabilidad

| Parte | Valor |
|---|---|
| **Estímulo** | El volumen de simulaciones y evaluaciones sube a 8× el normal y se sostiene. |
| **Fuente del estímulo** | Una campaña comercial que coincide con una quincena de pago. |
| **Artefacto** | Servicios de Simulación y Scoring y la fachada. |
| **Entorno** | Pico sostenido de 30 minutos con enrutamiento parcial (por ejemplo, 50 % hacia los servicios nuevos). Una dependencia del monolito se degrada durante la prueba. |
| **Respuesta esperada** | Los servicios escalan horizontalmente. Si la parte nueva agota su presupuesto de error, el *circuit breaker* o la fachada devuelve el tráfico al monolito sin que el cliente lo note. |
| **Medida de la respuesta** | Disponibilidad **≥ 99,5 %** durante el pico (*error budget* ≤ 0,5 % de peticiones fallidas). Escalado a la capacidad necesaria en **< 2 minutos**. Si se agota el *error budget*, el tráfico vuelve al monolito en **< 5 minutos** con **0 peticiones perdidas** atribuibles a la conmutación. |
| **Medida real** | *(semana 7)* |

#### Consistencia

| Parte | Valor |
|---|---|
| **Estímulo** | El porcentaje de enrutamiento de Scoring sube (canary 10 % → 50 %) y luego se revierte al 0 % por un fallo. |
| **Fuente del estímulo** | El equipo de operación, siguiendo el plan de despliegue progresivo, o una alarma automática. |
| **Artefacto** | Fachada strangler, servicio de Scoring y registro de decisiones del monolito. |
| **Entorno** | Coexistencia: el monolito es dueño de la solicitud y Scoring emite decisiones para una fracción del tráfico. |
| **Respuesta esperada** | Cada solicitud tiene **una sola decisión vigente**, con un identificador de correlación único que permite saber quién la decidió (monolito o servicio nuevo), con qué versión de reglas y por qué. La reversión no deja decisiones huérfanas ni duplicadas. |
| **Medida de la respuesta** | **100 %** de las solicitudes del periodo de prueba son reconciliables (una decisión y un lado identificado). Hay **0 decisiones duplicadas o huérfanas** en el reporte de reconciliación. Para una solicitud puntual, la pregunta "¿quién la resolvió y por qué?" se responde con evidencia en **< 5 minutos**. |
| **Medida real** | *(semana 7)* |

#### Evolutividad

| Parte | Valor |
|---|---|
| **Estímulo** | Un desarrollador propone un cambio al contrato OpenAPI de Simulación o Scoring, por ejemplo renombrar o eliminar un campo de la respuesta. |
| **Fuente del estímulo** | El equipo de desarrollo, en un PR. |
| **Artefacto** | El contrato OpenAPI publicado (`/v1`) y el pipeline de CI. |
| **Entorno** | Tiempo de integración, con agregadores fintech, la app y el agente de IA consumiendo `v1` en producción. |
| **Respuesta esperada** | El *gate* de CI detecta el breaking change y bloquea el merge, salvo que se publique como nueva versión mayor (`v2`) con convivencia y una política de deprecación. Los cambios aditivos pasan sin fricción. |
| **Medida de la respuesta** | **100 %** de los breaking changes detectados y bloqueados en CI (verificado con PR de prueba). **0 consumidores de `v1` rotos**. La política de deprecación garantiza **≥ 6 meses** de convivencia entre versiones mayores (🟡 a confirmar en ADR). |
| **Medida real** | *(semanas 2 y 7)* |

### 6.4 Historial de versiones de la rúbrica

| Versión | Semana | Qué cambió |
|---|---|---|
| **v0.1** | 1 | Priorización inicial y escenarios de calidad con medidas como meta. |
| v0.2 | 4 | Medida real de rendimiento (resultado de k6 bajo el escenario de pico). |
| v0.3 | 5 | Medida real de seguridad (prueba de BOLA, *scope* del agente, amenaza STRIDE). |
| v0.4 | 7 | Medidas reales de escalabilidad, mantenibilidad y evolutividad (error budget, circuit breaker, gate de CI). |
| v1.0 | 8 | Rúbrica consolidada con medida real para los seis atributos. Es la versión que se sustenta ante el comité. |

---

## 7. Dudas para el tutor

| ID | Duda | Por qué importa | Estado |
|---|---|---|---|
| T-01 | ¿Los repositorios F1 y F2 corresponden obligatoriamente a Simulación y Scoring (por los roles del enunciado), o el equipo puede elegir otros módulos? | Define si D-01 es abierta o ya está acotada por el curso. | 🟡 Por enviar |
| T-02 | ¿El monolito base expone ya algún mecanismo de integración (API interna, eventos, acceso a la base de datos) o hay que construir la anticorrupción desde cero? | Afecta la estrategia de consistencia y la carga de la fachada. | 🟡 Por enviar |
| T-03 | ¿Hay cifras de referencia de volumen (solicitudes por hora, relación simulación/solicitud) o el equipo las define como supuestos? | Calibra las medidas de rendimiento y escalabilidad. | 🟡 Por enviar |
| T-04 | ¿Qué infraestructura de despliegue se espera (local con Docker Compose, nube, Kubernetes)? | Afecta cómo se miden la escalabilidad y el *rollback*. | 🟡 Por enviar |
| T-05 | ¿Se espera un proveedor de identidad concreto (OAuth 2.0 / OIDC, FAPI) para simular el perfil de seguridad de open finance? | Define el modelo de *scopes* para agregadores y para el agente de IA. | 🟡 Por enviar |
| T-06 | ¿El agente de IA debe implementarse o basta con diseñar y defender su alcance de acceso? | Define el esfuerzo de la semana 5 y siguientes. | 🟡 Por enviar |
| T-07 | ¿El SAD y la rúbrica se entregan en la wiki de GitHub del repositorio base o en otro medio? | Logística del entregable. | 🟡 Por enviar |

---

## 8. Checklist del entregable de la semana 1

- [ ] Acta de Inicio completa: integrantes y roles, horario, líder, alcance acordado y restricciones (§1).
- [ ] El acta identifica los **tres roles** y define al **líder** (D-02, D-03).
- [ ] Reglas de Funcionamiento: **≥ 5 reglas verificables**, con al menos una de comunicación, puntualidad, colaboración y calidad del trabajo (§2.7).
- [ ] Rúbrica de Atributos de Calidad v0.1 con prioridades justificadas y seis escenarios de seis partes (§6).
- [ ] Dudas registradas y enviadas al tutor (§7).
- [ ] Grabación de la reunión publicada en la wiki, sección **"Seguimiento del proyecto"**.
- [ ] Todas las decisiones 🟡 del §0 resueltas y marcadas ✅.
- [ ] Visto bueno del tutor (prerrequisito para la semana 2).
