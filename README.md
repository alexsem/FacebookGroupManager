# Facebook Group Batch Poster con Playwright

Script en Python modular y orientado a objetos para publicar en múltiples grupos de Facebook (100+ grupos) divididos en tandas (por defecto tandas de 10), con control de cadencia, reanudación automática y perfil persistente para evitar bloqueos.

---

## 🚀 Características

- **Publicación por Tandas (Batches)**: Divide la lista de grupos en lotes de 10 grupos (o configurable en `.env`).
- **Generadores de Memoria Eficiente**: Lectura de archivos y streaming de grupos mediante generadores (`yield`) para evitar consumo excesivo de memoria.
- **Perfil de Navegador Persistente**: Inicias sesión manualmente una sola vez (`--login`) con soporte de 2FA. Tu sesión queda guardada localmente en la carpeta `fb_user_data/` y no expones contraseñas en código.
- **Evasión de Detección Anti-Bot**:
  - Tipeo con variaciones de tiempo humano entre caracteres (`FB_HUMAN_TYPING`).
  - Esperas aleatorias configurables entre publicaciones (ej. 45 a 90 segundos).
  - Tiempo de enfriamiento (cooldown) entre tandas (ej. 10 minutos entre cada tanda de 10 grupos).
  - Detección de bloqueos de acción y detención de emergencia para resguardar la cuenta.
- **Historial y Reanudación Automática (`post_history.json`)**: Si el proceso se interrumpe o cancela, al volver a ejecutarlo continuará solo con los grupos pendientes sin repetir los ya publicados.
- **Soporte de Imagen Opcional**: Posibilidad de adjuntar una foto o imagen a la publicación.

---

## 📁 Estructura del Proyecto

- [`main.py`](file:///d:/OneDrive/Documentos/Scripts/main.py): Interfaz CLI principal con comandos `--login`, `--run`, `--dry-run`, `--single`.
- [`poster.py`](file:///d:/OneDrive/Documentos/Scripts/poster.py): Clase `FacebookGroupPoster` encargada de interactuar con el DOM de Facebook mediante Playwright.
- [`batch_manager.py`](file:///d:/OneDrive/Documentos/Scripts/batch_manager.py): Clase `GroupBatchManager` que gestiona el streaming por tandas y el estado en JSON.
- [`config.py`](file:///d:/OneDrive/Documentos/Scripts/config.py): Carga y validación de variables de entorno desde `.env` o `.env.local`.
- [`groups.txt`](file:///d:/OneDrive/Documentos/Scripts/groups.txt): Archivo de entrada con las URLs de los grupos de Facebook (una por línea).
- [`post_content.txt`](file:///d:/OneDrive/Documentos/Scripts/post_content.txt): Archivo con el texto del mensaje a publicar.
- [`.env`](file:///d:/OneDrive/Documentos/Scripts/.env): Variables de configuración de tiempos, tandas y opciones.

---

## 🛠️ Instalación y Requisitos

El entorno virtual ya fue inicializado con `uv` en `.venv` con Python 3.12 y los navegadores de Playwright instalados.

Para activar el entorno virtual en PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

Si necesitas reinstalar dependencias o navegadores en otra máquina:
```powershell
uv pip install -r requirements.txt
playwright install chromium
```

---

## 📋 Guía de Uso Paso a Paso

### 1. Iniciar Sesión por Primera Vez (Login Persistente)

Ejecuta el siguiente comando para abrir el navegador Chromium y guardar tu sesión:

```powershell
.venv\Scripts\python.exe main.py --login
```

1. Se abrirá una ventana de Facebook.
2. Ingresa tu correo, contraseña y código de autenticación en dos pasos (2FA) si lo tienes habilitado.
3. Una vez que estés en tu muro o feed principal de Facebook, regresa a la consola y presiona `ENTER`.
4. La sesión quedará guardada de forma segura en `fb_user_data/` (ignorado por Git).

---

### 2. Configurar Grupos y Mensaje

1. Edita el archivo [`groups.txt`](file:///d:/OneDrive/Documentos/Scripts/groups.txt) y pega la lista de grupos (hasta 100 o más), uno por línea:
   ```text
   https://www.facebook.com/groups/123456789/
   https://www.facebook.com/groups/ventas.zona.norte/
   ```
2. Edita [`post_content.txt`](file:///d:/OneDrive/Documentos/Scripts/post_content.txt) con el mensaje que se publicará.
3. (Opcional) Si quieres adjuntar una imagen, coloca la ruta en la variable `FB_IMAGE_PATH` dentro de [`.env`](file:///d:/OneDrive/Documentos/Scripts/.env).

---

### 3. Probar en un Solo Grupo (Dry Run o Real)

Para verificar que los selectores y la interacción funcionen correctamente en un grupo de prueba sin riesgo:

```powershell
# Modo simulación (no presiona "Publicar")
.venv\Scripts\python.exe main.py --single "https://www.facebook.com/groups/TU_GRUPO/" --dry-run

# O prueba real en un solo grupo:
.venv\Scripts\python.exe main.py --single "https://www.facebook.com/groups/TU_GRUPO/"
```

---

### 4. Ejecutar la Campaña por Tandas

Para iniciar la publicación en los 100+ grupos divididos en lotes de 10:

```powershell
.venv\Scripts\python.exe main.py --run
```

**Flujo de ejecución:**
1. Publica en el Grupo 1.
2. Espera entre 45 y 90 segundos aleatorios.
3. Repite hasta completar el Grupo 10.
4. **Pausa de enfriamiento (cooldown)**: Espera 10 minutos (600s) para que los algoritmos de Facebook no detecten ráfagas de spam.
5. Inicia automáticamente la Tanda 2 (Grupos 11 a 20) y así sucesivamente hasta completar los 100 grupos.

---

## ⚙️ Configuración Avanzada (`.env`)

| Variable | Valor por Defecto | Descripción |
|---|---|---|
| `FB_BATCH_SIZE` | `10` | Cantidad de grupos por tanda. |
| `FB_MIN_POST_DELAY` | `45` | Segundos mínimos de espera entre grupos de una tanda. |
| `FB_MAX_POST_DELAY` | `90` | Segundos máximos de espera entre grupos de una tanda. |
| `FB_BATCH_COOLDOWN` | `600` | Segundos de pausa entre tandas completadas (600 = 10 min). |
| `FB_HEADLESS` | `false` | Navegador visible (`false`) o en segundo plano (`true`). |
| `FB_HUMAN_TYPING` | `true` | Simula tecleo humano carácter por carácter. |
| `FB_IMAGE_PATH` | *(vacío)* | Ruta a archivo de imagen a adjuntar (`ej: banner.png`). |
