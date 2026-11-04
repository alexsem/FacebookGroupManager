# Facebook Group Batch Poster con Playwright

Script en Python modular y orientado a objetos para publicar en múltiples grupos de Facebook (100+ grupos) divididos en tandas (por defecto lotes de 10), con control de cadencia humana, reanudación automática, perfil persistente y soporte para paquetes de contenido (texto + múltiples imágenes + videos en una misma publicación).

---

## ⚡ Comandos Rápidos (Copiar y Pegar)

> Abre tu terminal de PowerShell en la carpeta del proyecto (`d:\OneDrive\Documentos\Scripts`) antes de ejecutar:

### 1. Iniciar sesión por primera vez (Solo se hace una vez)
Abre Chrome nativo para ingresar con tu cuenta y guardar la sesión persistente en `fb_user_data/`:
```powershell
.venv\Scripts\python.exe main.py --login
```

---

### 2. Probar en un solo grupo (Simulación / Dry-Run)
Navega al grupo, escribe el texto y adjunta la foto y el video, pero **no hace clic en Publicar**:
```powershell
.venv\Scripts\python.exe main.py --single "https://www.facebook.com/groups/1887266828711361/" --path "moto_electrica_uruz" --dry-run
```

---

### 3. Publicar de verdad en un solo grupo
Realiza la publicación efectiva en ese grupo específico:
```powershell
.venv\Scripts\python.exe main.py --single "https://www.facebook.com/groups/1887266828711361/" --path "moto_electrica_uruz"
```

---

### 4. Simulación de la campaña completa (Dry-Run en todos los grupos)
Recorre todos los grupos de `groups.txt` simulando la carga en cada uno sin publicar:
```powershell
.venv\Scripts\python.exe main.py --run --path "moto_electrica_uruz" --dry-run
```

---

### 5. Lanzar la campaña real en todos los grupos (Por tandas)
Publica automáticamente en todos los grupos configurados en `groups.txt` con pausas anti-bot y cooldown entre tandas:
```powershell
.venv\Scripts\python.exe main.py --run --path "moto_electrica_uruz"
```

---

### 6. Ejecución con opciones avanzadas

* **Cambiar el tamaño de la tanda a 5 grupos (en vez de 10):**
  ```powershell
  .venv\Scripts\python.exe main.py --run --path "moto_electrica_uruz" --batch-size 5
  ```

* **Usar una lista de grupos alternativa (ej. groups_test.txt):**
  ```powershell
  .venv\Scripts\python.exe main.py --groups-file "groups_test.txt" --path "moto_electrica_uruz"
  ```
  ```

* **Ejecutar con la carpeta de post por defecto (`post_data/`):**
  ```powershell
  .venv\Scripts\python.exe main.py --run
  ```

* **Ver el menú de ayuda con todos los parámetros disponibles:**
  ```powershell
  .venv\Scripts\python.exe main.py --help
  ```

---

## 📁 Cómo Estructurar una Carpeta de Publicación

Puedes crear cualquier carpeta (como `moto_electrica_uruz/` o `post_data/`) con la siguiente estructura:

```text
nombre_de_tu_carpeta/
├── post_content.txt        <-- Texto del mensaje (soporta emojis y saltos de línea)
├── foto_1.jpeg             <-- Imagen (JPG, PNG, WebP)
├── foto_2.png              <-- Más imágenes (opcional)
└── video_demo.mp4          <-- Video (MP4, MOV, MKV, etc.)
```

> **Nota:** Todos los archivos de imagen y video dentro de la carpeta se adjuntan **a la misma publicación**. El script detecta el progreso de subida de Facebook y espera automáticamente a que el video y fotos terminen de procesarse antes de continuar.

---

## ⚙️ Configuración y Variables de Entorno (`.env`)

En el archivo [`.env`](file:///d:/OneDrive/Documentos/Scripts/.env) puedes ajustar el comportamiento del bot:

| Variable | Descripción | Valor por Defecto |
| :--- | :--- | :--- |
| `FB_POST_DIR` | Carpeta con texto y multimedia si no usas `--path` | `post_data` |
| `FB_GROUPS_FILE` | Archivo con las URLs de grupos de Facebook | `groups.txt` |
| `FB_USER_DATA_DIR` | Directorio donde se guarda la sesión de Chrome | `fb_user_data` |
| `FB_HISTORY_FILE` | Archivo donde se registra el progreso | `post_history.json` |
| `FB_BATCH_SIZE` | Cantidad de grupos por tanda | `10` |
| `FB_MIN_POST_DELAY` | Espera mínima entre publicaciones (segundos) | `45` |
| `FB_MAX_POST_DELAY` | Espera máxima entre publicaciones (segundos) | `90` |
| `FB_BATCH_COOLDOWN` | Pausa de descanso entre tandas (segundos: 600 = 10 min) | `600` |
| `FB_HEADLESS` | `false` para ver el navegador, `true` para segundo plano | `false` |
| `FB_HUMAN_TYPING` | Simular tipeo humano con variaciones de tiempo | `true` |

---

## 🔄 Reanudación Automática e Historial

Cada vez que un grupo se procesa exitosamente (o queda pendiente de aprobación del administrador), se registra en [`post_history.json`](file:///d:/OneDrive/Documentos/Scripts/post_history.json).

* **Si la ejecución se interrumpe** (por corte de luz, cierre manual, etc.), al volver a ejecutar el comando `--run` continuará **únicamente con los grupos pendientes**, sin repetir los que ya fueron publicados.
* **Si deseas volver a publicar en todos los grupos desde cero**, simplemente elimina o renombra el archivo `post_history.json`:
  ```powershell
  Remove-Item post_history.json -ErrorAction SilentlyContinue
  ```

---

## 🛡️ Medidas de Seguridad Anti-Bloqueo Integradas

1. **Perfil persistente (`fb_user_data/`):** Utiliza cookies y tokens reales de tu Chrome habitual sin exponer contraseñas en scripts.
2. **Sin indicadores de automatización:** Se eliminaron las banderas `--enable-automation` y `--no-sandbox` para evitar alertas en Meta.
3. **Pausas aleatorias (Jitter):** Espera entre 45 y 90 segundos entre cada post simulando comportamiento humano.
4. **Pausa entre tandas (Cooldown):** Descanso configurable (10 minutos por defecto) cada 10 grupos para evitar límites de cadencia de Facebook.
5. **Detección de rate limits:** Si Facebook muestra un aviso de acción bloqueada o límite temporal, el script se detiene de inmediato automáticamente para resguardar la cuenta.
