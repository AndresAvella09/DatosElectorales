# Metodología de Muestreo y Análisis de Datos

Este documento describe el enfoque estadístico y metodológico utilizado para la recolección de datos en el proyecto **DatosElectorales-2026**.

## 1. Naturaleza del Muestreo
El sistema utiliza un **muestreo no probabilístico**, clasificado principalmente como:
*   **Muestreo Intencional o por Juicio**: La selección de los datos está guiada por criterios temáticos específicos (palabras clave electorales como "elecciones Colombia 2026", "candidatos presidenciales", etc.).
*   **Muestreo por Conveniencia**: La recolección está sujeta a la disponibilidad técnica de las APIs y las limitaciones de las interfaces de las redes sociales.

## 2. Estrategia de Recolección
### Fuentes y Criterios
*   **YouTube**: Muestreo basado en relevancia y frescura (bias de los últimos 7 días), capturando una estructura jerárquica (Video -> Comentarios -> Respuestas).
*   **Twitter/X**: Muestreo basado en el flujo "Live" (reciente) mediante operadores de búsqueda específicos y simulación de usuario real para reducir bloqueos.

### Unidades de Análisis
Se recolectan no solo los mensajes principales (posts/videos), sino también la **conversación periférica** (comentarios/replies) y métricas de **engagement** (likes, retweets, views), lo que permite un análisis de redes y flujos discursivos.

## 3. Sesgos Identificados
Es fundamental reconocer los siguientes sesgos para la interpretación correcta de los resultados:
1.  **Sesgo Algorítmico**: Las plataformas priorizan contenido basado en sus propios algoritmos de relevancia, engagement y viralidad, lo que puede amplificar voces extremas.
2.  **Sesgo de Selección**: Al usar palabras clave, se excluyen discursos que utilicen terminología alternativa, ironía o lenguaje cifrado que no coincida con los términos de búsqueda.
3.  **Sesgo de Representatividad**: Los usuarios activos en X y YouTube no representan proporcionalmente a la población votante total de Colombia. Los resultados reflejan el **discurso digital**, no necesariamente la opinión pública general del país.

## 4. Uso Sugerido de los Datos
Los datos recolectados son aptos para:
*   Identificación de **narrativas emergentes** y temas de agenda (Agenda Setting).
*   Análisis de **sentimiento, polarización y emociones** en el discurso.
*   Detección de "frames" discursivos y evolución temporal de temas políticos.

**Nota**: Estos datos **no deben utilizarse** para realizar inferencias estadísticas sobre intención de voto poblacional o como sustituto de encuestas electorales probabilísticas.
