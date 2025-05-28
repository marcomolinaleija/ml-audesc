# **Generador de Audiodescripciones para Video: Documentación para el Usuario**

Esta aplicación te permite integrar audiodescripciones personalizadas en videos.

## **1. Selección y Carga del Archivo de Video**

Para iniciar, debes cargar el archivo de video sobre el cual deseas trabajar. Hay dos métodos para esto:

* **Arrastrar y Soltar:** Puedes arrastrar directamente tu archivo de video (formatos compatibles: MP4, AVI, MOV, MKV) al campo de texto etiquetado como "Archivo de Video".
* **Exploración Manual:** Alternativamente, haz clic en el botón "Seleccionar Video..." para abrir un cuadro de diálogo y navegar por los directorios de tu sistema para localizar y seleccionar el archivo deseado.

Una vez que el video ha sido seleccionado, la aplicación mostrará automáticamente su duración en el campo "Duración:".

## **2. Gestión de Audiodescripciones**

Esta sección te permite añadir, editar y organizar las audiodescripciones dentro de tu proyecto.

* **Agregar Audiodescripción:**
    * Haz clic en el botón "Agregar Audiodescripción".
    * Se abrirá una ventana de diálogo donde deberás especificar el tiempo exacto en el video donde deseas insertar la audiodescripción. Puedes introducir el tiempo en formato HH:MM:SS o directamente en segundos.
    * Posteriormente, se te solicitará seleccionar el archivo de audio que contiene la audiodescripción (formatos compatibles: WAV, MP3, M4A, AAC).
    * Opcionalmente, puedes introducir una breve descripción textual para identificar la audiodescripción en la lista.
    * La audiodescripción se añadirá a la tabla principal, mostrando el tiempo de inicio, el nombre del archivo de audio y su descripción.
* **Editar Audiodescripción:** Selecciona una audiodescripción de la lista y haz clic en el botón "Editar", o haz doble clic sobre el elemento. Podrás modificar el tiempo de inicio, el archivo de audio asociado y la descripción.
* **Eliminar Audiodescripción:** Selecciona la audiodescripción que deseas remover de la lista y presiona el botón "Eliminar". Se te pedirá una confirmación antes de proceder con la eliminación.

## **3. Funcionalidades de Gestión de Proyectos**

La aplicación ofrece opciones para guardar y recuperar tus proyectos:

* **Importar Proyecto:** Utiliza este botón para cargar un proyecto previamente guardado desde un archivo JSON. Esto restaurará la configuración del video, las audiodescripciones y los ajustes de salida.
* **Exportar Proyecto:** Permite guardar el estado actual del proyecto (video seleccionado, audiodescripciones y configuraciones) en un archivo JSON, lo que te permite reanudar tu trabajo en otro momento o compartirlo.
* **Guardar proyecto como...:** Utiliza esta opción para guardar el proyecto actual con un nuevo nombre o en una ubicación diferente.
* **Limpiar Proyecto:** Esta función borra todos los datos del proyecto actual, incluyendo el video cargado, las audiodescripciones y las configuraciones de salida. Se solicitará una confirmación antes de ejecutar esta acción.
* **Guardado Automático:** La aplicación realiza guardados automáticos periódicos del estado de su proyecto para prevenir la pérdida de datos en caso de cierre inesperado.

## **4. Configuración de Salida**

Antes de generar el video final, puedes ajustar los siguientes parámetros:

* **Archivo de Salida:** Especifica el nombre y la ruta donde se guardará el video resultante con las audiodescripciones integradas. Por defecto, se sugerirá un nombre basado en el archivo de video original.
* **Volumen Original:** Ajusta el nivel de volumen del audio original del video.
* **Volumen Descripción:** Modifica el nivel de volumen de las audiodescripciones.

## **5. Generación y Previsualización del Video Final**

Una vez configurados todos los elementos, puedes proceder a la creación del video:

* **Generar Video con Audiodescripción:** Al hacer clic en este botón, la aplicación comenzará el proceso de mezcla del video original con las audiodescripciones y el audio ajustado. Este proceso puede tomar tiempo, dependiendo de la duración del video y la complejidad del proyecto. El progreso se indicará mediante una barra de carga y mensajes de estado.
* **Previsualizar Video:** Para verificar la sincronización y el volumen de las audiodescripciones antes de la generación final, puedes utilizar el botón "Previsualizar Video". Se creará una versión temporal del video con las audiodescripciones, que se abrirá en tu reproductor multimedia predeterminado. Los archivos de previsualización se eliminan automáticamente al cerrar la aplicación.