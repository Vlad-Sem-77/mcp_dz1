"""
Клиент для Trivago MCP-сервера (поиск отелей).

Официальный эндпоинт: https://mcp.trivago.com/mcp

Теперь Trivago предоставляет инструмент `trivago-accommodation-search`,
который принимает `query` (название города) напрямую. Для лучшей точности
мы дополнительно геокодируем город через Nominatim и передаем координаты.

Поддерживаемые инструменты:
    - trivago-accommodation-search (query или lat/lng + arrival/departure)
    - trivago-accommodation-radius-search (lat/lng + arrival/departure)
"""

import json
import httpx

from travel_backend.mcp_clients.base_mcp_client import BaseMCPClient, MCPError

TRIVAGO_MCP_ENDPOINT = "https://mcp.trivago.com/mcp"


class TrivagoClient:
    def __init__(self):
        self._client = BaseMCPClient(TRIVAGO_MCP_ENDPOINT, server_name="Trivago")
        self._initialized = False
        self._geocoder = httpx.Client(timeout=10.0)

    def ensure_initialized(self):
        if not self._initialized:
            self._client.initialize()
            self._initialized = True

    def _geocode_city(self, city: str) -> tuple[float | None, float | None]:
        """Геокодирует город через Nominatim (OpenStreetMap)."""
        try:
            resp = self._geocoder.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": city,
                    "format": "json",
                    "limit": 1,
                },
                headers={"User-Agent": "ai-travel-agent/1.0"},
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception:
            pass
        return None, None

    def _iso_country_from_city(self, city: str) -> str:
        """Угадать ISO-код страны по городу (простой эвристический список)."""
        city_lower = city.lower()
        city_to_country = {
            "berlin": "DE", "munich": "DE", "hamburg": "DE", "cologne": "DE", "frankfurt": "DE",
            "vienna": "AT", "prague": "CZ", "budapest": "HU", "warsaw": "PL",
            "paris": "FR", "lyon": "FR", "nice": "FR", "marseille": "FR",
            "rome": "IT", "milan": "IT", "naples": "IT", "venice": "IT", "florence": "IT",
            "barcelona": "ES", "madrid": "ES", "valencia": "ES", "seville": "ES",
            "amsterdam": "NL", "rotterdam": "NL",
            "london": "GB", "manchester": "GB", "edinburgh": "GB", "birmingham": "GB",
            "lisbon": "PT", "porto": "PT",
            "athens": "GR", "thessaloniki": "GR",
            "copenhagen": "DK", "stockholm": "SE", "oslo": "NO", "helsinki": "FI",
            "zurich": "CH", "geneva": "CH", "basel": "CH",
            "brussels": "BE", "bruges": "BE",
            "dublin": "IE", "reykjavik": "IS",
            "istanbul": "TR", "antalya": "TR",
            "dubai": "AE", "abu dhabi": "AE",
            "new york": "US", "los angeles": "US", "chicago": "US", "san francisco": "US",
            "miami": "US", "las vegas": "US", "boston": "US", "seattle": "US",
            "toronto": "CA", "vancouver": "CA", "montreal": "CA",
            "sydney": "AU", "melbourne": "AU", "brisbane": "AU",
            "tokyo": "JP", "osaka": "JP", "kyoto": "JP",
            "singapore": "SG", "hong kong": "HK",
            "bangkok": "TH", "phuket": "TH", "chiang mai": "TH",
            "seoul": "KR", "busan": "KR",
            "mumbai": "IN", "delhi": "IN", "bangalore": "IN", "chennai": "IN",
            "cairo": "EG", "alexandria": "EG",
            "tel aviv": "IL", "jerusalem": "IL",
            "jakarta": "ID", "bali": "ID",
            "kuala lumpur": "MY", "penang": "MY",
            "manila": "PH", "cebu": "PH",
            "sao paulo": "BR", "rio de janeiro": "BR",
            "buenos aires": "AR", "mexico city": "MX", "cancun": "MX",
            "bogota": "CO", "lima": "PE", "santiago": "CL",
            "cape town": "ZA", "johannesburg": "ZA",
            "moscow": "RU", "st petersburg": "RU", "saint petersburg": "RU",
            "kiev": "UA", "kyiv": "UA", "lviv": "UA", "odessa": "UA",
            "minsk": "BY", "tallinn": "EE", "riga": "LV", "vilnius": "LT",
            "bucharest": "RO", "cluj": "RO",
            "sofia": "BG", "varna": "BG",
            "zagreb": "HR", "split": "HR", "dubrovnik": "HR",
            "belgrade": "RS", "sarajevo": "BA",
            "ljubljana": "SI", "skopje": "MK", "podgorica": "ME",
            "tirana": "AL", "pristina": "XK",
            "chisinau": "MD", "tbilisi": "GE", "yerevan": "AM",
            "baku": "AZ", "astana": "KZ", "almaty": "KZ",
        }
        return city_to_country.get(city_lower, "US")

    def search_hotels(
        self,
        city: str,
        checkin: str,
        checkout: str,
        adults: int = 1,
        country: str | None = None,
        currency: str = "EUR",
    ) -> dict:
        """
        Ищет отели через Trivago MCP.
        city — название города на английском.
        checkin / checkout — формат YYYY-MM-DD.
        Попробует сначала через query, если не сработает — через координаты.
        """
        self.ensure_initialized()

        if not country:
            country = self._iso_country_from_city(city)

        # Попробуем сначала через query (более простой путь)
        try:
            result = self._client.call_tool(
                "trivago-accommodation-search",
                {
                    "query": city,
                    "adults": adults,
                    "arrival": checkin,
                    "departure": checkout,
                    "country": country,
                    "currency": currency,
                },
            )
            # Если результат не содержит ошибки и есть отели — возвращаем
            if "error" not in result or "output" not in result:
                content = result.get("content", [])
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        # Проверяем что это не ошибка
                        if "An error occurred" not in text or "output" in text:
                            return result
                # Если ошибка — попробуем через координаты
                pass
        except MCPError:
            pass

        # Fallback: геокодируем и используем координаты
        lat, lng = self._geocode_city(city)
        if lat and lng:
            try:
                return self._client.call_tool(
                    "trivago-accommodation-search",
                    {
                        "latitude": lat,
                        "longitude": lng,
                        "adults": adults,
                        "arrival": checkin,
                        "departure": checkout,
                        "country": country,
                        "currency": currency,
                    },
                )
            except MCPError as exc:
                return {"error": str(exc)}

        return {"error": f"Не удалось найти отели для города '{city}' через Trivago"}

    def close(self):
        self._client.close()
        try:
            self._geocoder.close()
        except Exception:
            pass
