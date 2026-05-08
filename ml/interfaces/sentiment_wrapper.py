"""
sentiment_wrapper.py — Interfaz abstracta para modelos de sentimiento.

PARA EL EQUIPO DE Desarrollo                                               
Esta clase define el CONTRATO entre el pipeline de datos y los   
modelos de sentimiento. El equipo de ML debe crear una clase que 
herede de SentimentModelWrapper e implemente predict().          
                                                                 
El pipeline de datos solo interactúa con esta interfaz, así que  
el modelo puede cambiarse libremente sin romper nada.            

Ejemplo de implementación:

    class MyBERTSentiment(SentimentModelWrapper):
        def __init__(self):
            super().__init__(model_name="bert-sentiment-es", version="1.0")
            self.model = load_my_model()

        def predict(self, texts):
            results = self.model(texts)
            return [
                SentimentResult(label=r["label"], score=r["score"])
                for r in results
            ]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SentimentResult:
    """Resultado de predicción de sentimiento para un texto."""
    label: str    # "positive", "negative", "neutral"
    score: float  # Confianza del modelo [0.0, 1.0]


class SentimentModelWrapper(ABC):
    """
    Interfaz abstracta que todo modelo de sentimiento debe implementar.

    El pipeline de datos solo usará predict() para obtener resultados.
    """

    def __init__(self, model_name: str = "unknown", version: str = "0.0"):
        self.model_name = model_name
        self.version = version

    @abstractmethod
    def predict(self, texts: list[str]) -> list[SentimentResult]:
        """
        Predice el sentimiento para una lista de textos.

        Args:
            texts: Lista de strings (text_clean de la capa Gold).

        Returns:
            Lista de SentimentResult, uno por texto, en el mismo orden.
        """
        ...

    def get_info(self) -> dict:
        """Retorna metadatos del modelo para logging y tracking."""
        return {"model_name": self.model_name, "version": self.version}


class DummySentimentModel(SentimentModelWrapper):
    """
    Modelo dummy para testing. Siempre retorna 'neutral' con score 0.5.
    Reemplazar con la implementación real del equipo de ML.
    """

    def __init__(self):
        super().__init__(model_name="dummy", version="0.0-test")

    def predict(self, texts: list[str]) -> list[SentimentResult]:
        return [SentimentResult(label="neutral", score=0.5) for _ in texts]
