# ML — Modelos de Análisis de Sentimiento

> Este directorio contiene las **interfaces y wrappers** que conectan el pipeline de datos con los modelos de ML.

## Estructura

```
ml/
├── interfaces/
│   └── sentiment_wrapper.py   # Clase abstracta SentimentModelWrapper
└── registry/                  # Tracking de experimentos (por implementar)
```

## Para el equipo de Desarrollo

1. Crear una clase que herede de `SentimentModelWrapper`
2. Implementar el método `predict(texts: list[str]) -> list[SentimentResult]`
3. El pipeline llamará a esta interfaz automáticamente en la capa Gold

Ver [`sentiment_wrapper.py`](interfaces/sentiment_wrapper.py) para ejemplos y documentación.
