# Facebook Group Batch Poster con Playwright

Script en Python modular y orientado a objetos para publicar en múltiples grupos de Facebook (100+ grupos) divididos en tandas (por defecto tandas de 10), con control de cadencia, reanudación automática, perfil persistente y soporte para carpetas de contenido (texto + imágenes + videos).

---

## 🚀 Características

- **Publicación por Tandas (Batches)**: Divide la lista de grupos en lotes de 10 grupos (configurable en `.env`).
- **Paquete de Contenido Unificado (Directorio de Post)**: En lugar de archivos sueltos, indicas una carpeta con `--path` donde colocas `post_content.txt` junto con todas las imágenes y videos que van en el mismo post.
- **Soporte Multimedia Combinado**: Adjunta múltiples imágenes (.jpg, .jpeg, .png, etc.) y/o videos (.mp4, .mov, etc.) a la misma publicación con detección de carga en Facebook.
- **Generadores de Memoria Eficiente**: Lectura de archivos y streaming de grupos mediante generadores (`yield`) para evitar consumo excesivo de memoria.
- **Perfil de Navegador Persistente**: Inicias sesión manualmente una sola vez (`--login`) con soporte de 2FA. Tu sesión queda guardada localmente en la carpeta `fb_user_data/` y no expones contraseñas en código.
- **Evasión de Detección Anti-Bot**:
  - Tipeo con variaciones de tiempo humano entre caracteres (`FB_HUMAN_TYPING`).
  - Esperas aleatorias configurables entre publicaciones (ej. 45 a 90 segundos).
  - Tiempo de enfriamiento (cooldown) entre tandas (ej. 10 minutos entre cada tanda de 10 grupos).
  - Detección de bloqueos de acción y detención de emergencia para resguardar la cuenta.
- **Historial y Reanudación Automática (`post_history.json`)**: Si el proceso se interrumpe, al volver a ejecutarlo continuará solo con los grupos pendientes sin repetir los ya publicados.

---

## 📁 Estructura del Proyecto

- [`main.py`](file:///d:/OneDrive/Documentos/Scripts/main.py): Interfaz CLI principal con comandos `--login`, `--run`, `--dry-run`, `--single`, `--path`.
- [`post_bundle.py`](file:///d:/OneDrive/Documentos/Scripts/post_bundle.py): Clases `PostBundle` y `PostBundleLoader` que descubren el texto y los archivos multimedia (fotos/videos) en una carpeta.
- [`poster.py`](file:///d:/OneDrive/Documentos/Scripts/poster.py): Clase `FacebookGroupPoster` encargada de interactuar con el DOM de Facebook mediante Playwright y esperar la subida multimedia.
- [`batch_manager.py`](file:///d:/OneDrive/Documentos/Scripts/batch_manager.py): Clase `GroupBatchManager` que gestiona el streaming por tandas y el estado en JSON.
- [`config.py`](file:///d:/OneDrive/Documentos/Scripts/config.py): Carga y validación de variables de entorno desde `.env` o `.env.local`.
- [`post_data/`](file:///d:/OneDrive/Documentos/Scripts/post_data): Carpeta por defecto con `post_content.txt` y archivos multimedia.
- [`groups.txt`](file:///d:/OneDrive/Documentos/Scripts/groups.txt): Archivo de entrada con las URLs de los grupos de Facebook (una por línea).
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

### 2. Preparar tu Contenido (Carpeta con Texto + Imágenes/Videos)

Crea una carpeta (o usa la carpeta por defecto [`post_data/`](file:///d:/OneDrive/Documentos/Scripts/post_data)) y coloca dentro:
1. `post_content.txt`: con el mensaje de la publicación.
2. Cualquier imagen (.jpg, .png, etc.) y/o video (.mp4, .mov, etc.) que quieras adjuntar al post. Todos los archivos multimedia dentro de esa carpeta se subirán juntos al mismo post.

---

### 3. Probar en un Solo Grupo (Dry Run o Real)

Para verificar que los selectores y la subida de fotos/videos funcionen correctamente sin riesgo:

```powershell
# Modo simulación (escribe el post y adjunta los archivos, pero NO hace clic en "Publicar"):
.venv\Scripts\python.exe main.py --single "https://www.facebook.com/groups/TU_GRUPO/" --path "post_data" --dry-run

# O prueba de publicación real en un solo grupo:
.venv\Scripts\python.exe main.py --single "https://www.facebook.com/groups/TU_GRUPO/" --path "post_data"
```

---

### 4. Ejecutar la Campaña por Tandas

Para iniciar la publicación en todos los grupos de [`groups.txt`](file:///d:/OneDrive/Documentos/Scripts/groups.txt) divididos en lotes de 10:

```powershell
.venv\Scripts\python.exe main.py --run --path "post_data"
```
*(Si no pasas `--path`, usará automáticamente la carpeta configurada en `FB_POST_DIR` dentro de `.env`, que por defecto es `post_data`).*
